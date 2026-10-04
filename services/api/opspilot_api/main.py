import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from opspilot_persistence.db.engine import create_db_engine
from opspilot_api.middleware import install_correlation_middleware
from opspilot_persistence.repositories.base import RepositoryUnavailableError, RequestRepository
from opspilot_persistence.repositories.postgres import PostgresRequestRepository
from opspilot_api.routes import health, requests
from opspilot_api.settings import Settings
from opspilot_common.logging import configure_logging

from opspilot_messaging import EventPublisher, KafkaEventPublisher, InMemoryEventPublisher
from opspilot_rag import MockEmbedder, VectorStore

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, 
    repository: RequestRepository | None = None,
    publisher: EventPublisher | None = None,
    vector_store: VectorStore | None = None
) -> FastAPI:
    """Build the app. Pass `repository` in tests; otherwise PostgreSQL is used (lazily)."""
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)

    engine = None
    if repository is None:
        engine = create_db_engine(settings.database_url)
        repository = PostgresRequestRepository(engine)
        
    if publisher is None:
        if settings.mock_mode:
            publisher = InMemoryEventPublisher()
        else:
            publisher = KafkaEventPublisher(settings.kafka_bootstrap_servers)

    if vector_store is None:
        embedder = MockEmbedder() # Later we can use a real one if not mock_mode
        vector_store = VectorStore(embedder)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            engine.dispose()
        if publisher is not None:
            publisher.flush()

    app = FastAPI(title="OpsPilot API", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.request_repository = repository
    app.state.publisher = publisher
    app.state.vector_store = vector_store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from opspilot_common.telemetry import setup_telemetry
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from prometheus_client import make_asgi_app

    setup_telemetry("opspilot_api")
    FastAPIInstrumentor.instrument_app(app)
    
    # Mount Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    install_correlation_middleware(app)
    app.include_router(health.router)
    app.include_router(requests.router)

    from opspilot_api.routes import documents
    app.include_router(documents.router)

    @app.exception_handler(RepositoryUnavailableError)
    async def database_unavailable(_: Request, __: RepositoryUnavailableError) -> JSONResponse:
        logger.error("database_unavailable")
        return JSONResponse(
            status_code=503, content={"detail": "Database temporarily unavailable. Retry later."}
        )

    logger.info(
        "api_started", extra={"environment": settings.environment, "mock_mode": settings.mock_mode}
    )
    return app
