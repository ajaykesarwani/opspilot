import pytest
from fastapi.testclient import TestClient

from opspilot_api.main import create_app
from opspilot_api.settings import Settings
from opspilot_messaging import InMemoryEventPublisher
from opspilot_persistence.repositories.memory import InMemoryRequestRepository


@pytest.fixture
def repository() -> InMemoryRequestRepository:
    return InMemoryRequestRepository()


@pytest.fixture
def publisher() -> InMemoryEventPublisher:
    return InMemoryEventPublisher()


@pytest.fixture
def client(repository: InMemoryRequestRepository, publisher: InMemoryEventPublisher) -> TestClient:
    # _env_file=None keeps tests independent of any local .env file.
    settings = Settings(_env_file=None, mock_mode=True, event_backend="memory")
    return TestClient(create_app(settings, repository, publisher))
