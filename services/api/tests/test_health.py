from fastapi.testclient import TestClient

from opspilot_api.main import create_app
from opspilot_persistence.repositories.memory import InMemoryRequestRepository
from opspilot_api.settings import Settings


class UnavailableRepository(InMemoryRequestRepository):
    def ping(self) -> bool:
        return False


def test_healthz_returns_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "opspilot-api"}


def test_readyz_returns_ready_when_database_is_up(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


def test_readyz_returns_503_when_database_is_down() -> None:
    app = create_app(Settings(_env_file=None), UnavailableRepository())
    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"database": "unavailable"}}


def test_healthz_stays_ok_when_database_is_down() -> None:
    """Liveness must not depend on the database (alive vs. ready)."""
    app = create_app(Settings(_env_file=None), UnavailableRepository())
    assert TestClient(app).get("/healthz").status_code == 200


def test_readyz_with_real_engine_and_unreachable_database() -> None:
    """No mock: a real engine pointed at a closed port must report not_ready, not crash."""
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/none",
    )
    client = TestClient(create_app(settings))
    assert client.get("/healthz").status_code == 200
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable"}
