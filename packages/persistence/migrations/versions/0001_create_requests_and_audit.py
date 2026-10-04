"""create requests and audit_events

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Frozen copy on purpose: a migration must not change when application enums change.
STATUSES = (
    "RECEIVED",
    "VALIDATED",
    "QUEUED",
    "PROCESSING",
    "AWAITING_REVIEW",
    "COMPLETED",
    "FAILED",
    "DEAD_LETTERED",
)


def upgrade() -> None:
    status_list = ", ".join(f"'{s}'" for s in STATUSES)
    op.create_table(
        "requests",
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("requester", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_requests_idempotency_key"),
        sa.CheckConstraint(f"status IN ({status_list})", name="ck_requests_status"),
        sa.CheckConstraint("retry_count >= 0", name="ck_requests_retry_count_non_negative"),
    )
    op.create_index("ix_requests_status_created_at", "requests", ["status", "created_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.request_id"],
            name="fk_audit_events_request_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_requests_status_created_at", table_name="requests")
    op.drop_table("requests")
