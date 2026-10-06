"""Request/response contracts for the public REST API."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from opspilot_contracts.workflow import WorkflowStatus

DISCLAIMER = (
    "Outputs are recommendations only. A human must review and approve any proposed action."
)


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class OperationalRequestCreate(BaseModel):
    """Body of POST /api/v1/requests."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=10_000)
    requester: str = Field(min_length=1, max_length=100)
    priority: Priority = Priority.NORMAL


class RequestAccepted(BaseModel):
    """Response of POST /api/v1/requests (202 new, 200 idempotent replay)."""

    request_id: UUID
    correlation_id: str
    status: WorkflowStatus
    created_at: datetime
    disclaimer: str = DISCLAIMER


class RequestDetail(BaseModel):
    """Response of GET /api/v1/requests/{request_id}."""

    request_id: UUID
    correlation_id: str
    status: WorkflowStatus
    request: OperationalRequestCreate
    result: dict[str, Any] | None = None
    error_code: str | None = None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    disclaimer: str = DISCLAIMER
