"""Typed Kafka event contracts (schema version 1) and topic names. Pure data, no I/O."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from opspilot_contracts.requests import Priority
from opspilot_contracts.workflow import WorkflowStatus

SCHEMA_VERSION = 1
CORRELATION_ID_PATTERN = r"^[A-Za-z0-9._-]{8,64}$"


@dataclass(frozen=True)
class Topics:
    """Topic names. `prefix` isolates test runs on a shared broker; it is empty in normal use."""

    prefix: str = ""

    @property
    def requested(self) -> str:
        return f"{self.prefix}workflow.requested"

    @property
    def completed(self) -> str:
        return f"{self.prefix}workflow.completed"

    @property
    def failed(self) -> str:
        return f"{self.prefix}workflow.failed"

    @property
    def dlq(self) -> str:
        return f"{self.prefix}workflow.dlq"

    def all(self) -> tuple[str, ...]:
        return (self.requested, self.completed, self.failed, self.dlq)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _EventCommon(_Strict):
    # Literal[1]: a message with any other version fails validation and is dead-lettered
    # instead of being processed under assumptions that may no longer hold.
    schema_version: Literal[1] = SCHEMA_VERSION
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    # Number of processing attempts this event reflects (1 = first). Producers set 1; events the
    # worker emits after retries carry the attempts used.
    attempt: int = Field(default=1, ge=1, le=100)


class _WorkflowEvent(_EventCommon):
    request_id: UUID
    correlation_id: str = Field(pattern=CORRELATION_ID_PATTERN)


# ---- payloads ----


class WorkflowRequestedPayload(_Strict):
    """Deliberately small: the worker loads the full request from PostgreSQL (single source of
    truth), so request text is not duplicated into Kafka."""

    priority: Priority


class WorkflowCompletedPayload(_Strict):
    """Processing finished. The workflow now waits for human review; it is NOT approved."""

    status: WorkflowStatus
    processor: str


class WorkflowFailedPayload(_Strict):
    final_status: Literal[WorkflowStatus.FAILED, WorkflowStatus.DEAD_LETTERED]
    error_code: str = Field(max_length=64)
    error_message: str = Field(max_length=500)


class DeadLetterReason(StrEnum):
    MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
    REQUEST_NOT_FOUND = "REQUEST_NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"
    RETRIES_EXHAUSTED = "RETRIES_EXHAUSTED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class DeadLetterPayload(_Strict):
    reason: DeadLetterReason
    error_message: str = Field(max_length=500)
    source_topic: str
    source_partition: int | None = None
    source_offset: int | None = None
    # Raw original bytes (decoded with replacement), truncated; absent when not applicable.
    original_message: str | None = Field(default=None, max_length=8192)


# ---- events ----


class WorkflowRequestedEvent(_WorkflowEvent):
    event_type: Literal["workflow.requested"] = "workflow.requested"
    payload: WorkflowRequestedPayload


class WorkflowCompletedEvent(_WorkflowEvent):
    event_type: Literal["workflow.completed"] = "workflow.completed"
    payload: WorkflowCompletedPayload


class WorkflowFailedEvent(_WorkflowEvent):
    event_type: Literal["workflow.failed"] = "workflow.failed"
    payload: WorkflowFailedPayload


class DeadLetterEvent(_EventCommon):
    """A malformed message may carry no usable request or correlation ID, so both are optional."""

    event_type: Literal["workflow.dlq"] = "workflow.dlq"
    request_id: UUID | None = None
    correlation_id: str | None = None
    payload: DeadLetterPayload
