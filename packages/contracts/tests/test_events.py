import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from opspilot_contracts import (
    DeadLetterEvent,
    DeadLetterPayload,
    DeadLetterReason,
    Priority,
    Topics,
    WorkflowCompletedEvent,
    WorkflowCompletedPayload,
    WorkflowFailedEvent,
    WorkflowFailedPayload,
    WorkflowRequestedEvent,
    WorkflowRequestedPayload,
    WorkflowStatus,
)

CORR = "corr-0123456789"


def make_event(**overrides) -> dict:
    data = {
        "request_id": str(uuid4()),
        "correlation_id": CORR,
        "payload": {"priority": "high"},
    }
    data.update(overrides)
    return data


def test_valid_event_has_required_envelope_fields_and_defaults() -> None:
    event = WorkflowRequestedEvent.model_validate(make_event())
    assert event.schema_version == 1
    assert event.event_type == "workflow.requested"
    assert event.attempt == 1
    assert event.event_id is not None
    assert event.timestamp.tzinfo is not None
    assert event.payload.priority is Priority.HIGH


def test_json_round_trip_is_lossless() -> None:
    original = WorkflowRequestedEvent(
        request_id=uuid4(),
        correlation_id=CORR,
        payload=WorkflowRequestedPayload(priority=Priority.LOW),
    )
    parsed = WorkflowRequestedEvent.model_validate_json(original.model_dump_json())
    assert parsed == original
    assert json.loads(original.model_dump_json())["schema_version"] == 1


def test_each_event_gets_a_unique_event_id() -> None:
    a = WorkflowRequestedEvent.model_validate(make_event())
    b = WorkflowRequestedEvent.model_validate(make_event())
    assert a.event_id != b.event_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 2},  # unknown future version is rejected, not guessed at
        {"schema_version": 0},
        {"request_id": "not-a-uuid"},
        {"correlation_id": "short"},
        {"correlation_id": "has spaces in it!!"},
        {"timestamp": "2026-10-04T10:00:00"},  # naive timestamp
        {"attempt": 0},
        {"event_type": "workflow.completed"},
        {"payload": {"priority": "urgent"}},
        {"payload": {"priority": "low", "extra": 1}},
        {"unexpected": "field"},
    ],
    ids=[
        "future-schema",
        "schema-zero",
        "bad-request-id",
        "short-correlation",
        "bad-correlation-chars",
        "naive-timestamp",
        "attempt-zero",
        "wrong-event-type",
        "bad-priority",
        "extra-payload-field",
        "extra-envelope-field",
    ],
)
def test_invalid_events_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        WorkflowRequestedEvent.model_validate(make_event(**overrides))


@pytest.mark.parametrize("missing", ["request_id", "correlation_id", "payload"])
def test_missing_required_fields_are_rejected(missing: str) -> None:
    data = make_event()
    del data[missing]
    with pytest.raises(ValidationError):
        WorkflowRequestedEvent.model_validate(data)


def test_events_are_immutable() -> None:
    event = WorkflowRequestedEvent.model_validate(make_event())
    with pytest.raises(ValidationError):
        event.attempt = 5


def test_completed_and_failed_events() -> None:
    completed = WorkflowCompletedEvent(
        request_id=uuid4(),
        correlation_id=CORR,
        payload=WorkflowCompletedPayload(status=WorkflowStatus.AWAITING_REVIEW, processor="mock"),
    )
    assert completed.event_type == "workflow.completed"

    failed = WorkflowFailedEvent(
        request_id=uuid4(),
        correlation_id=CORR,
        attempt=3,
        payload=WorkflowFailedPayload(
            final_status=WorkflowStatus.DEAD_LETTERED, error_code="X", error_message="boom"
        ),
    )
    assert failed.attempt == 3
    with pytest.raises(ValidationError):  # only FAILED / DEAD_LETTERED are valid final states
        WorkflowFailedPayload(
            final_status=WorkflowStatus.COMPLETED, error_code="X", error_message="no"
        )


def test_dead_letter_event_allows_missing_ids_for_malformed_input() -> None:
    event = DeadLetterEvent(
        payload=DeadLetterPayload(
            reason=DeadLetterReason.MALFORMED_MESSAGE,
            error_message="not json",
            source_topic="workflow.requested",
            original_message="{oops",
        )
    )
    assert event.request_id is None and event.correlation_id is None
    assert event.timestamp <= datetime.now(UTC)


def test_topic_names_and_prefix() -> None:
    assert Topics().all() == (
        "workflow.requested",
        "workflow.completed",
        "workflow.failed",
        "workflow.dlq",
    )
    assert Topics(prefix="t1.").requested == "t1.workflow.requested"
