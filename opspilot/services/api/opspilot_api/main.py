import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import make_asgi_app

from opspilot_api.middleware import install_correlation_middleware
from opspilot_api.routes import documents, health, requests
from opspilot_api.settings import Settings
from opspilot_common.logging import configure_logging
from opspilot_common.telemetry import setup_telemetry
from opspilot_messaging import EventPublisher, InMemoryEventPublisher, KafkaEventPublisher
from opspilot_persistence.db.engine import create_db_engine
from opspilot_persistence.repositories.base import RepositoryUnavailableError, RequestRepository
from opspilot_persistence.repositories.postgres import PostgresRequestRepository
from opspilot_rag import MockEmbedder, VectorStore, load_knowledge_base

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    repository: RequestRepository | None = None,
    publisher: EventPublisher | None = None,
    vector_store: VectorStore | None = None,
) -> FastAPI:
    """Build the app. Pass collaborators in tests; otherwise PostgreSQL/Kafka are used."""
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)
    setup_telemetry("opspilot_api")

    engine = None
    if repository is None:
        engine = create_db_engine(settings.database_url)
        repository = PostgresRequestRepository(engine)

    if publisher is None:
        publisher = (
            InMemoryEventPublisher()
            if settings.event_backend == "memory"
            else KafkaEventPublisher(settings.kafka_bootstrap_servers)
        )

    if vector_store is None:
        vector_store = VectorStore(MockEmbedder())  # swap for a real embedder when mock_mode=False
        load_knowledge_base(vector_store, settings.knowledge_base_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        publisher.flush()
        if engine is not None:
            engine.dispose()

    app = FastAPI(title="OpsPilot API", version="0.3.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.request_repository = repository
    app.state.publisher = publisher
    app.state.vector_store = vector_store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID", "Idempotent-Replayed"],
    )
    FastAPIInstrumentor.instrument_app(app)
    app.mount("/metrics", make_asgi_app())

    install_correlation_middleware(app)
    app.include_router(health.router)
    app.include_router(requests.router)
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
