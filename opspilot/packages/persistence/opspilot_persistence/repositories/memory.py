"""In-memory repository: a TEST DOUBLE for fast tests without Docker.

It is never used at runtime and runs through the same contract tests as the PostgreSQL
implementation so the two cannot drift apart.
"""

import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from opspilot_contracts import WorkflowStatus, assert_transition
from opspilot_persistence.repositories.base import (
    EVENT_REQUEST_RECEIVED,
    EVENT_STATUS_CHANGED,
    AuditRecord,
    CreateOutcome,
    IdempotencyConflictError,
    NewRequest,
    RequestNotFoundError,
    RequestRecord,
)


class InMemoryRequestRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[UUID, RequestRecord] = {}
        self._by_key: dict[str, UUID] = {}
        self._audit: dict[UUID, list[AuditRecord]] = {}

    def create_or_get(self, new: NewRequest) -> CreateOutcome:
        with self._lock:
            existing_id = self._by_key.get(new.idempotency_key)
            if existing_id is not None:
                existing = self._records[existing_id]
                if existing.fingerprint != new.fingerprint:
                    raise IdempotencyConflictError(new.idempotency_key)
                return CreateOutcome(existing, created=False)

            now = datetime.now(UTC)
            self._records[new.request_id] = RequestRecord(
                request_id=new.request_id,
                correlation_id=new.correlation_id,
                idempotency_key=new.idempotency_key,
                fingerprint=new.fingerprint,
                status=WorkflowStatus.RECEIVED,
                payload=new.payload,
                result=None,
                error_code=None,
                retry_count=0,
                created_at=now,
                updated_at=now,
            )
            self._by_key[new.idempotency_key] = new.request_id
            self._audit[new.request_id] = [
                AuditRecord(
                    EVENT_REQUEST_RECEIVED,
                    None,
                    WorkflowStatus.RECEIVED,
                    new.payload.requester,
                    new.correlation_id,
                    None,
                    now,
                )
            ]
            record = self._apply_transition(
                new.request_id, WorkflowStatus.VALIDATED, "api", new.correlation_id
            )
            return CreateOutcome(record, created=True)

    def get(self, request_id: UUID) -> RequestRecord | None:
        return self._records.get(request_id)

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
        with self._lock:
            return self._apply_transition(
                request_id, new_status, actor, correlation_id, result, error_code, increment_retry
            )

    def _apply_transition(
        self,
        request_id: UUID,
        new_status: WorkflowStatus,
        actor: str,
        correlation_id: str,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        increment_retry: bool = False,
    ) -> RequestRecord:
        current = self._records.get(request_id)
        if current is None:
            raise RequestNotFoundError(str(request_id))
        assert_transition(current.status, new_status)
        now = datetime.now(UTC)
        updated = replace(
            current,
            status=new_status,
            result=result if result is not None else current.result,
            error_code=error_code if error_code is not None else current.error_code,
            retry_count=current.retry_count + (1 if increment_retry else 0),
            updated_at=now,
        )
        self._records[request_id] = updated
        self._audit[request_id].append(
            AuditRecord(
                EVENT_STATUS_CHANGED,
                current.status,
                new_status,
                actor,
                correlation_id,
                None,
                now,
            )
        )
        return updated

    def audit_trail(self, request_id: UUID) -> list[AuditRecord]:
        return list(self._audit.get(request_id, []))

    def ping(self) -> bool:
        return True
