from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from opspilot_persistence.db.models import AuditEventRow, RequestRow
from opspilot_persistence.repositories.base import (
    EVENT_REQUEST_RECEIVED,
    EVENT_STATUS_CHANGED,
    AuditRecord,
    CreateOutcome,
    IdempotencyConflictError,
    NewRequest,
    RepositoryUnavailableError,
    RequestNotFoundError,
    RequestRecord,
)
from opspilot_contracts import OperationalRequestCreate, WorkflowStatus, assert_transition


@contextmanager
def _translate_db_errors() -> Iterator[None]:
    """Connection-level failures become RepositoryUnavailableError (-> HTTP 503)."""
    try:
        yield
    except (OperationalError, InterfaceError) as exc:
        raise RepositoryUnavailableError("database unavailable") from exc


def _to_record(row: RequestRow) -> RequestRecord:
    return RequestRecord(
        request_id=row.request_id,
        correlation_id=row.correlation_id,
        idempotency_key=row.idempotency_key,
        fingerprint=row.request_fingerprint,
        status=WorkflowStatus(row.status),
        payload=OperationalRequestCreate.model_validate(row.payload),
        result=row.result,
        error_code=row.error_code,
        retry_count=row.retry_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresRequestRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_or_get(self, new: NewRequest) -> CreateOutcome:
        now = datetime.now(UTC)
        with _translate_db_errors(), self._sessions.begin() as session:
            # The UNIQUE constraint on idempotency_key decides races between concurrent
            # submissions: exactly one INSERT wins, the others see no returned row.
            inserted = session.execute(
                pg_insert(RequestRow)
                .values(
                    request_id=new.request_id,
                    correlation_id=new.correlation_id,
                    idempotency_key=new.idempotency_key,
                    request_fingerprint=new.fingerprint,
                    status=WorkflowStatus.RECEIVED.value,
                    priority=new.payload.priority.value,
                    requester=new.payload.requester,
                    payload=new.payload.model_dump(mode="json"),
                    retry_count=0,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(RequestRow.request_id)
            ).scalar_one_or_none()

            if inserted is None:
                existing = session.execute(
                    select(RequestRow).where(RequestRow.idempotency_key == new.idempotency_key)
                ).scalar_one()
                if existing.request_fingerprint != new.fingerprint:
                    raise IdempotencyConflictError(new.idempotency_key)
                return CreateOutcome(_to_record(existing), created=False)

            session.add(
                AuditEventRow(
                    request_id=new.request_id,
                    event_type=EVENT_REQUEST_RECEIVED,
                    from_status=None,
                    to_status=WorkflowStatus.RECEIVED.value,
                    actor=new.payload.requester,
                    correlation_id=new.correlation_id,
                    detail=None,
                    created_at=now,
                )
            )
            row = self._apply_transition(
                session, new.request_id, WorkflowStatus.VALIDATED, "api", new.correlation_id
            )
            return CreateOutcome(_to_record(row), created=True)

    def get(self, request_id: UUID) -> RequestRecord | None:
        with _translate_db_errors(), self._sessions() as session:
            row = session.get(RequestRow, request_id)
            return _to_record(row) if row else None

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
        with _translate_db_errors(), self._sessions.begin() as session:
            row = self._apply_transition(
                session,
                request_id,
                new_status,
                actor,
                correlation_id,
                result,
                error_code,
                increment_retry,
            )
            return _to_record(row)

    @staticmethod
    def _apply_transition(
        session: Session,
        request_id: UUID,
        new_status: WorkflowStatus,
        actor: str,
        correlation_id: str,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        increment_retry: bool = False,
    ) -> RequestRow:
        # FOR UPDATE serialises concurrent transitions on the same request.
        row = session.execute(
            select(RequestRow).where(RequestRow.request_id == request_id).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise RequestNotFoundError(str(request_id))

        current = WorkflowStatus(row.status)
        assert_transition(current, new_status)

        now = datetime.now(UTC)
        row.status = new_status.value
        row.updated_at = now
        if result is not None:
            row.result = result
        if error_code is not None:
            row.error_code = error_code
        if increment_retry:
            row.retry_count = row.retry_count + 1
        session.add(
            AuditEventRow(
                request_id=request_id,
                event_type=EVENT_STATUS_CHANGED,
                from_status=current.value,
                to_status=new_status.value,
                actor=actor,
                correlation_id=correlation_id,
                detail=None,
                created_at=now,
            )
        )
        return row

    def audit_trail(self, request_id: UUID) -> list[AuditRecord]:
        with _translate_db_errors(), self._sessions() as session:
            rows = session.scalars(
                select(AuditEventRow)
                .where(AuditEventRow.request_id == request_id)
                .order_by(AuditEventRow.id)
            ).all()
            return [
                AuditRecord(
                    event_type=r.event_type,
                    from_status=WorkflowStatus(r.from_status) if r.from_status else None,
                    to_status=WorkflowStatus(r.to_status) if r.to_status else None,
                    actor=r.actor,
                    correlation_id=r.correlation_id,
                    detail=r.detail,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    def ping(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False
