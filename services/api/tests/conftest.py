import pytest
from fastapi.testclient import TestClient

from opspilot_api.main import create_app
from opspilot_api.settings import Settings
from opspilot_persistence.repositories.memory import InMemoryRequestRepository


@pytest.fixture
def repository() -> InMemoryRequestRepository:
    return InMemoryRequestRepository()


@pytest.fixture
def client(repository: InMemoryRequestRepository) -> TestClient:
    # _env_file=None keeps tests independent of any local .env file.
    settings = Settings(_env_file=None, mock_mode=True)
    return TestClient(create_app(settings, repository))
