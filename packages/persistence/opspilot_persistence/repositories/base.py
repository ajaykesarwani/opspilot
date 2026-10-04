"""Repository interface, records and errors. Implementations: memory.py (test double) and
postgres.py (runtime)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from opspilot_contracts import OperationalRequestCreate, WorkflowStatus

EVENT_REQUEST_RECEIVED = "request_received"
EVENT_STATUS_CHANGED = "status_changed"


class RepositoryError(Exception):
    pass


class RepositoryUnavailableError(RepositoryError):
    """The backing store could not be reached."""


class IdempotencyConflictError(RepositoryError):
    """The idempotency key was already used with a different payload."""


class RequestNotFoundError(RepositoryError):
    pass


@dataclass(frozen=True)
class NewRequest:
    request_id: UUID
    correlation_id: str
    idempotency_key: str
    fingerprint: str
    payload: OperationalRequestCreate


@dataclass(frozen=True)
class RequestRecord:
    request_id: UUID
    correlation_id: str
    idempotency_key: str
    fingerprint: str
    status: WorkflowStatus
    payload: OperationalRequestCreate
    result: dict[str, Any] | None
    error_code: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AuditRecord:
    event_type: str
    from_status: WorkflowStatus | None
    to_status: WorkflowStatus | None
    actor: str
    correlation_id: str
    detail: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True)
class CreateOutcome:
    record: RequestRecord
    created: bool  # False means an idempotent replay of an existing request


class RequestRepository(Protocol):
    def create_or_get(self, new: NewRequest) -> CreateOutcome:
        """Persist a new request (RECEIVED -> VALIDATED) or return the existing one for the same
        idempotency key. Raises IdempotencyConflictError if the payload differs."""
        ...

    def get(self, request_id: UUID) -> RequestRecord | None: ...

    def transition(
        self,
        request_id: UUID,
        new_status: WorkflowStatus,
        *,
        actor: str,
        correlation_id: str,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        increment_retry: bool = False,
    ) -> RequestRecord:
        """Apply a validated state change and audit it atomically.
        Raises RequestNotFoundError or InvalidTransitionError."""
        ...

    def audit_trail(self, request_id: UUID) -> list[AuditRecord]: ...

    def ping(self) -> bool:
        """Cheap reachability check used by /readyz."""
        ...
