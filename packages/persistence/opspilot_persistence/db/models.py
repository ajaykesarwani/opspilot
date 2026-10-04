from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from opspilot_contracts import WorkflowStatus

_STATUS_LIST = ", ".join(f"'{s.value}'" for s in WorkflowStatus)


class Base(DeclarativeBase):
    pass


class RequestRow(Base):
    __tablename__ = "requests"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_requests_idempotency_key"),
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="ck_requests_status"),
        CheckConstraint("retry_count >= 0", name="ck_requests_retry_count_non_negative"),
        Index("ix_requests_status_created_at", "status", "created_at"),
    )

    request_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(16))
    requester: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    """Append-only audit trail. Rows are never updated or deleted by the application."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_request_id", "request_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("requests.request_id", ondelete="RESTRICT", name="fk_audit_events_request_id"),
    )
    event_type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
