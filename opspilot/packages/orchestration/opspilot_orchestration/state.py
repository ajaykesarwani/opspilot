from typing import Literal

from pydantic import BaseModel, Field

from opspilot_contracts.requests import OperationalRequestCreate

ConfidenceCategory = Literal["high", "medium", "low", "insufficient_evidence"]
FinalStatus = Literal["AWAITING_REVIEW", "FAILED"]


class Recommendation(BaseModel):
    summary: str
    requested_action: str
    missing_information: str | None = None
    recommended_next_step: str
    confidence_category: ConfidenceCategory
    citations: list[str] = Field(default_factory=list)
    limitation_disclaimer: str


class WorkflowState(BaseModel):
    request_id: str
    correlation_id: str
    request: OperationalRequestCreate

    is_valid: bool = True
    classification: str | None = None
    retrieved_chunks: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False

    recommendation: Recommendation | None = None
    validation_retries: int = 0
    max_retries: int = 3

    error: str | None = None
    # The graph never completes a request on its own: it ends in AWAITING_REVIEW (a human must
    # approve, see ADR 0003) or FAILED.
    final_status: FinalStatus | None = None
