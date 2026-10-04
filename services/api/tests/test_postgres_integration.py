"""End-to-end tests against real PostgreSQL (needs `docker compose up -d postgres`)."""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from opspilot_api.main import create_app
from opspilot_persistence.repositories.postgres import PostgresRequestRepository
from opspilot_api.settings import Settings

pytestmark = pytest.mark.integration

VALID = {
    "subject": "Customer escalation",
    "body": "Customer reports a repeated billing error and wants a refund.",
    "requester": "ops.agent",
}


@pytest.fixture
def pg_client(pg_repository: PostgresRequestRepository) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None), pg_repository))


def test_post_get_and_replay_through_postgres(
    pg_client: TestClient, pg_repository: PostgresRequestRepository
) -> None:
    headers = {"Idempotency-Key": "integration-key-1"}
    first = pg_client.post("/api/v1/requests", json=VALID, headers=headers)
    assert first.status_code == 202
    request_id = first.json()["request_id"]

    replay = pg_client.post("/api/v1/requests", json=VALID, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["request_id"] == request_id

    conflict = pg_client.post(
        "/api/v1/requests", json={**VALID, "subject": "Different"}, headers=headers
    )
    assert conflict.status_code == 409

    detail = pg_client.get(f"/api/v1/requests/{request_id}").json()
    assert detail["status"] == "VALIDATED"
    assert detail["request"]["requester"] == "ops.agent"

    with pg_repository._engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM requests")).scalar()
    assert count == 1  # replay and conflict created no duplicate work


def test_data_survives_a_new_app_instance(
    pg_client: TestClient, pg_repository: PostgresRequestRepository
) -> None:
    """Persistence, not process memory: a freshly built app still sees the row."""
    request_id = pg_client.post("/api/v1/requests", json=VALID).json()["request_id"]
    fresh = TestClient(create_app(Settings(_env_file=None), pg_repository))
    assert fresh.get(f"/api/v1/requests/{request_id}").status_code == 200


def test_readyz_ok_with_real_database(pg_client: TestClient) -> None:
    response = pg_client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}


def test_database_rejects_unknown_status(
    pg_client: TestClient, pg_repository: PostgresRequestRepository
) -> None:
    pg_client.post("/api/v1/requests", json=VALID)
    with pytest.raises(IntegrityError), pg_repository._engine.begin() as connection:
        connection.execute(text("UPDATE requests SET status = 'BOGUS'"))


def test_database_rejects_negative_retry_count(
    pg_client: TestClient, pg_repository: PostgresRequestRepository
) -> None:
    pg_client.post("/api/v1/requests", json=VALID)
    with pytest.raises(IntegrityError), pg_repository._engine.begin() as connection:
        connection.execute(text("UPDATE requests SET retry_count = -1"))


def test_migration_creates_expected_schema_and_round_trips(
    pg_engine: Engine, pg_alembic_config: Config
) -> None:
    tables = set(inspect(pg_engine).get_table_names())
    assert {"requests", "audit_events"} <= tables
    columns = {c["name"] for c in inspect(pg_engine).get_columns("requests")}
    assert {
        "request_id",
        "correlation_id",
        "idempotency_key",
        "status",
        "payload",
        "result",
        "error_code",
        "retry_count",
        "created_at",
        "updated_at",
    } <= columns

    try:
        command.downgrade(pg_alembic_config, "base")
        assert "requests" not in set(inspect(pg_engine).get_table_names())
    finally:
        command.upgrade(pg_alembic_config, "head")
    assert "requests" in set(inspect(pg_engine).get_table_names())
