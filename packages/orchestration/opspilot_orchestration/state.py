from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from opspilot_contracts.requests import OperationalRequestCreate

class Recommendation(BaseModel):
    summary: str
    requested_action: str
    missing_information: Optional[str] = None
    recommended_next_step: str
    confidence_category: Literal["high", "medium", "low", "insufficient_evidence"]
    citations: List[str] = Field(default_factory=list)
    limitation_disclaimer: str

class WorkflowState(BaseModel):
    request_id: str
    correlation_id: str
    request: OperationalRequestCreate
    
    # Internal state tracking
    is_valid: bool = True
    classification: Optional[str] = None
    retrieved_chunks: List[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    
    recommendation: Optional[Recommendation] = None
    validation_retries: int = 0
    max_retries: int = 3
    
    error: Optional[str] = None
    final_status: Optional[Literal["AWAITING_REVIEW", "COMPLETED", "FAILED"]] = None
