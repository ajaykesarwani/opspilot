from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from opspilot_api.main import create_app
from opspilot_persistence.repositories.base import RepositoryUnavailableError
from opspilot_persistence.repositories.memory import InMemoryRequestRepository
from opspilot_api.settings import Settings

VALID = {
    "subject": "Customer escalation",
    "body": "Customer reports a repeated billing error and wants a refund.",
    "requester": "ops.agent",
}


class BrokenRepository(InMemoryRequestRepository):
    def create_or_get(self, new):
        raise RepositoryUnavailableError("down")

    def get(self, request_id):
        raise RepositoryUnavailableError("down")


def test_create_request_returns_202_with_ids(
    client: TestClient, repository: InMemoryRequestRepository
) -> None:
    response = client.post("/api/v1/requests", json=VALID)
    assert response.status_code == 202
    body = response.json()
    request_id = UUID(body["request_id"])
    assert body["status"] == "VALIDATED"
    assert body["correlation_id"] == response.headers["X-Correlation-ID"]
    assert "recommendations only" in body["disclaimer"]
    assert "Idempotent-Replayed" not in response.headers
    stored = repository.get(request_id)
    assert stored is not None
    assert stored.payload.priority.value == "normal"


def test_create_request_accepts_explicit_priority(client: TestClient) -> None:
    response = client.post("/api/v1/requests", json={**VALID, "priority": "high"})
    assert response.status_code == 202


def test_requests_without_idempotency_key_are_distinct_work(client: TestClient) -> None:
    first = client.post("/api/v1/requests", json=VALID).json()
    second = client.post("/api/v1/requests", json=VALID).json()
    assert first["request_id"] != second["request_id"]


# ---- idempotency ----


def test_replayed_idempotency_key_returns_original_request(client: TestClient) -> None:
    headers = {"Idempotency-Key": "order-12345-submit"}
    first = client.post(
        "/api/v1/requests", json=VALID, headers={**headers, "X-Correlation-ID": "first-corr-0001"}
    )
    second = client.post(
        "/api/v1/requests", json=VALID, headers={**headers, "X-Correlation-ID": "second-corr-002"}
    )
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["request_id"] == first.json()["request_id"]
    # The body reports the ORIGINAL correlation ID; the header reflects this call.
    assert second.json()["correlation_id"] == "first-corr-0001"
    assert second.headers["X-Correlation-ID"] == "second-corr-002"


def test_omitted_default_priority_matches_explicit_default_on_replay(client: TestClient) -> None:
    headers = {"Idempotency-Key": "priority-default-1"}
    first = client.post("/api/v1/requests", json=VALID, headers=headers)
    second = client.post("/api/v1/requests", json={**VALID, "priority": "normal"}, headers=headers)
    assert second.status_code == 200
    assert second.json()["request_id"] == first.json()["request_id"]


def test_idempotency_key_reuse_with_different_payload_returns_409(client: TestClient) -> None:
    headers = {"Idempotency-Key": "conflicting-key-1"}
    assert client.post("/api/v1/requests", json=VALID, headers=headers).status_code == 202
    response = client.post(
        "/api/v1/requests", json={**VALID, "subject": "Another subject"}, headers=headers
    )
    assert response.status_code == 409
    assert "different request payload" in response.json()["detail"]


@pytest.mark.parametrize("key", ["short", "has spaces in it", "x" * 129, "bad/chars/here"])
def test_malformed_idempotency_key_returns_422(client: TestClient, key: str) -> None:
    response = client.post("/api/v1/requests", json=VALID, headers={"Idempotency-Key": key})
    assert response.status_code == 422


# ---- GET ----


def test_get_request_returns_persisted_state(client: TestClient) -> None:
    created = client.post("/api/v1/requests", json=VALID).json()
    response = client.get(f"/api/v1/requests/{created['request_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == created["request_id"]
    assert body["status"] == "VALIDATED"
    assert body["request"]["subject"] == VALID["subject"]
    assert body["result"] is None and body["error_code"] is None
    assert body["retry_count"] == 0


def test_get_unknown_request_returns_404(client: TestClient) -> None:
    assert client.get(f"/api/v1/requests/{uuid4()}").status_code == 404


def test_get_with_malformed_id_returns_422(client: TestClient) -> None:
    assert client.get("/api/v1/requests/not-a-uuid").status_code == 422


# ---- failure handling ----


def test_database_outage_returns_503_with_correlation_id() -> None:
    client = TestClient(create_app(Settings(_env_file=None), BrokenRepository()))
    response = client.post("/api/v1/requests", json=VALID)
    assert response.status_code == 503
    assert "X-Correlation-ID" in response.headers
    assert client.get(f"/api/v1/requests/{uuid4()}").status_code == 503


# ---- validation (unchanged from Milestone 1) ----


@pytest.mark.parametrize(
    "payload",
    [
        {k: v for k, v in VALID.items() if k != "subject"},  # missing field
        {**VALID, "subject": "ab"},  # too short
        {**VALID, "subject": "     "},  # blank after stripping
        {**VALID, "body": "too short"},  # body below minimum
        {**VALID, "body": "x" * 10_001},  # body above maximum
        {**VALID, "requester": ""},
        {**VALID, "priority": "urgent"},  # not in enum
        {**VALID, "unexpected": "field"},  # extra fields forbidden
    ],
    ids=[
        "missing-subject",
        "short-subject",
        "blank-subject",
        "short-body",
        "long-body",
        "empty-requester",
        "bad-priority",
        "extra-field",
    ],
)
def test_invalid_payload_returns_422_and_persists_nothing(
    client: TestClient, repository: InMemoryRequestRepository, payload: dict
) -> None:
    response = client.post("/api/v1/requests", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]
    assert repository._records == {}


def test_malformed_json_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/requests", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
