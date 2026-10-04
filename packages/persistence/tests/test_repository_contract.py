"""The same behavioural contract run against both repository implementations."""

import threading
from uuid import uuid4

import pytest

from opspilot_api.idempotency import payload_fingerprint
from opspilot_persistence.repositories.base import (
    EVENT_REQUEST_RECEIVED,
    EVENT_STATUS_CHANGED,
    IdempotencyConflictError,
    NewRequest,
    RequestNotFoundError,
    RequestRepository,
)
from opspilot_persistence.repositories.memory import InMemoryRequestRepository
from opspilot_contracts import InvalidTransitionError, OperationalRequestCreate, WorkflowStatus

S = WorkflowStatus


@pytest.fixture(
    params=["memory", pytest.param("postgres", marks=pytest.mark.integration)],
)
def repo(request: pytest.FixtureRequest) -> RequestRepository:
    if request.param == "memory":
        return InMemoryRequestRepository()
    return request.getfixturevalue("pg_repository")


def make_payload(**overrides: str) -> OperationalRequestCreate:
    data = {
        "subject": "Customer escalation",
        "body": "Customer reports a repeated billing error and wants a refund.",
        "requester": "ops.agent",
        **overrides,
    }
    return OperationalRequestCreate(**data)


def make_new(key: str | None = None, **overrides: str) -> NewRequest:
    payload = make_payload(**overrides)
    return NewRequest(
        request_id=uuid4(),
        correlation_id="corr-0123456789",
        idempotency_key=key or f"key-{uuid4().hex}",
        fingerprint=payload_fingerprint(payload),
        payload=payload,
    )


def advance(repo: RequestRepository, request_id, *statuses: S) -> None:
    for status in statuses:
        repo.transition(request_id, status, actor="test", correlation_id="corr-0123456789")


def test_create_persists_validated_request_with_audit_trail(repo: RequestRepository) -> None:
    outcome = repo.create_or_get(make_new())
    assert outcome.created
    record = outcome.record
    assert record.status is S.VALIDATED
    assert record.retry_count == 0
    assert record.result is None and record.error_code is None
    assert repo.get(record.request_id) == record

    trail = repo.audit_trail(record.request_id)
    assert [(e.event_type, e.from_status, e.to_status) for e in trail] == [
        (EVENT_REQUEST_RECEIVED, None, S.RECEIVED),
        (EVENT_STATUS_CHANGED, S.RECEIVED, S.VALIDATED),
    ]
    assert trail[0].actor == "ops.agent"
    assert all(e.correlation_id == "corr-0123456789" for e in trail)


def test_same_key_same_payload_returns_original(repo: RequestRepository) -> None:
    first = repo.create_or_get(make_new("shared-key-1"))
    second = repo.create_or_get(make_new("shared-key-1"))
    assert first.created and not second.created
    assert second.record.request_id == first.record.request_id
    assert len(repo.audit_trail(first.record.request_id)) == 2  # no duplicate work or audit


def test_same_key_different_payload_conflicts(repo: RequestRepository) -> None:
    repo.create_or_get(make_new("shared-key-2"))
    with pytest.raises(IdempotencyConflictError):
        repo.create_or_get(make_new("shared-key-2", subject="A different subject"))


def test_different_keys_create_distinct_requests(repo: RequestRepository) -> None:
    a = repo.create_or_get(make_new("key-aaaaaaaa"))
    b = repo.create_or_get(make_new("key-bbbbbbbb"))
    assert a.record.request_id != b.record.request_id


def test_get_unknown_returns_none(repo: RequestRepository) -> None:
    assert repo.get(uuid4()) is None


def test_full_happy_path_to_completed_stores_result(repo: RequestRepository) -> None:
    rid = repo.create_or_get(make_new()).record.request_id
    advance(repo, rid, S.QUEUED, S.PROCESSING, S.AWAITING_REVIEW)
    record = repo.transition(
        rid, S.COMPLETED, actor="reviewer", correlation_id="c-12345678", result={"decision": "ok"}
    )
    assert record.status is S.COMPLETED
    assert record.result == {"decision": "ok"}
    assert record.updated_at >= record.created_at
    trail = repo.audit_trail(rid)
    assert [e.to_status for e in trail][-1] is S.COMPLETED
    assert trail[-1].actor == "reviewer"


def test_illegal_transition_is_rejected_and_state_unchanged(repo: RequestRepository) -> None:
    rid = repo.create_or_get(make_new()).record.request_id
    trail_len = len(repo.audit_trail(rid))
    with pytest.raises(InvalidTransitionError):
        advance(repo, rid, S.COMPLETED)  # VALIDATED -> COMPLETED skips human review
    assert repo.get(rid).status is S.VALIDATED
    assert len(repo.audit_trail(rid)) == trail_len


def test_transition_unknown_request_raises(repo: RequestRepository) -> None:
    with pytest.raises(RequestNotFoundError):
        advance(repo, uuid4(), S.QUEUED)


def test_retry_edge_increments_retry_count(repo: RequestRepository) -> None:
    rid = repo.create_or_get(make_new()).record.request_id
    advance(repo, rid, S.QUEUED, S.PROCESSING)
    record = repo.transition(
        rid,
        S.QUEUED,
        actor="worker",
        correlation_id="c-12345678",
        error_code="LLM_TIMEOUT",
        increment_retry=True,
    )
    assert record.status is S.QUEUED
    assert record.retry_count == 1
    assert record.error_code == "LLM_TIMEOUT"


def test_dead_lettered_is_terminal(repo: RequestRepository) -> None:
    rid = repo.create_or_get(make_new()).record.request_id
    advance(repo, rid, S.QUEUED, S.DEAD_LETTERED)
    with pytest.raises(InvalidTransitionError):
        advance(repo, rid, S.QUEUED)


def test_concurrent_submissions_with_same_key_create_one_request(repo: RequestRepository) -> None:
    key = f"race-{uuid4().hex}"
    outcomes = []

    def submit() -> None:
        outcomes.append(repo.create_or_get(make_new(key)))

    threads = [threading.Thread(target=submit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(outcomes) == 8
    assert sum(o.created for o in outcomes) == 1
    assert len({o.record.request_id for o in outcomes}) == 1


def test_ping(repo: RequestRepository) -> None:
    assert repo.ping() is True
