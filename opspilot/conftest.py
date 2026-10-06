"""Shared test fixtures: PostgreSQL (real Alembic migrations) and Kafka availability.

Integration fixtures skip with a hint when the service is unreachable, unless
REQUIRE_DB_TESTS=1 / REQUIRE_KAFKA_TESTS=1 (set in CI), in which case they fail.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from opspilot_persistence.repositories.postgres import PostgresRequestRepository

ALEMBIC_INI = Path(__file__).parent / "packages" / "persistence" / "alembic.ini"
DEFAULT_TEST_DB_URL = "postgresql+psycopg://opspilot:opspilot@localhost:5432/opspilot_test"
DEFAULT_KAFKA = "localhost:29092"


def alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _ensure_database_exists(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def pg_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


@pytest.fixture(scope="session")
def pg_alembic_config(pg_url: str) -> Config:
    return alembic_config(pg_url)


@pytest.fixture(scope="session")
def pg_engine(pg_url: str) -> Iterator[Engine]:
    """Test database with the real Alembic migrations applied (this also tests the migrations)."""
    try:
        _ensure_database_exists(pg_url)
    except OperationalError as exc:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            raise
        pytest.skip(
            f"PostgreSQL not reachable ({type(exc).__name__}). Start it with: "
            "docker compose -f infra/docker-compose.yml up -d postgres"
        )
    command.upgrade(alembic_config(pg_url), "head")
    engine = create_engine(pg_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_clean(pg_engine: Engine) -> Engine:
    """The test engine with all tables emptied."""
    with pg_engine.begin() as connection:
        connection.execute(text("TRUNCATE audit_events, requests RESTART IDENTITY CASCADE"))
    return pg_engine


@pytest.fixture
def pg_repository(pg_clean: Engine) -> PostgresRequestRepository:
    return PostgresRequestRepository(pg_clean)


@pytest.fixture(scope="session")
def kafka_bootstrap() -> str:
    """Bootstrap servers of a reachable local Kafka, otherwise skip (or fail in CI)."""
    from confluent_kafka.admin import AdminClient

    servers = os.environ.get("TEST_KAFKA_BOOTSTRAP_SERVERS", DEFAULT_KAFKA)
    try:
        AdminClient({"bootstrap.servers": servers}).list_topics(timeout=5)
    except Exception as exc:
        if os.environ.get("REQUIRE_KAFKA_TESTS") == "1":
            raise
        pytest.skip(
            f"Kafka not reachable at {servers} ({type(exc).__name__}). Start it with: "
            "docker compose -f infra/docker-compose.yml up -d kafka"
        )
    return servers
