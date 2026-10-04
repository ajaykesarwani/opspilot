import logging
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Response, status

import datetime

from opspilot_api.deps import RepositoryDep, PublisherDep
from opspilot_api.idempotency import payload_fingerprint
from opspilot_persistence.repositories.base import IdempotencyConflictError, NewRequest
from opspilot_common.correlation import get_correlation_id, new_correlation_id
from opspilot_contracts import (
    OperationalRequestCreate,
    RequestAccepted,
    RequestDetail,
)
from opspilot_contracts.events import WorkflowRequestedEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])

IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Optional. Repeating a key returns the original request instead of new work.",
    ),
]


# Sync handlers: SQLAlchemy is blocking, so FastAPI runs these in its threadpool.
@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=RequestAccepted)
def create_request(
    payload: OperationalRequestCreate,
    repository: RepositoryDep,
    publisher: PublisherDep,
    response: Response,
    idempotency_key: IdempotencyKeyHeader = None,
) -> RequestAccepted:
    """Accept an operational request. Processing is asynchronous (added in later milestones).

    A replayed Idempotency-Key with the same payload returns 200 and the original request; with a
    different payload it returns 409.
    """
    new = NewRequest(
        request_id=uuid4(),
        # The middleware always sets one; the fallback only guards direct calls.
        correlation_id=get_correlation_id() or new_correlation_id(),
        # Without a caller key, a unique server key keeps every POST as distinct work.
        idempotency_key=idempotency_key or f"auto-{uuid4().hex}",
        fingerprint=payload_fingerprint(payload),
        payload=payload,
    )
    try:
        outcome = repository.create_or_get(new)
    except IdempotencyConflictError:
        logger.warning("idempotency_conflict")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different request payload.",
        ) from None

    record = outcome.record
    from opspilot_common.telemetry import request_count

    if outcome.created:
        logger.info(
            "request_accepted",
            extra={"request_id": str(record.request_id), "priority": payload.priority.value},
        )
        request_count.labels(endpoint="/requests", status="accepted").inc()
        
        # Publish the event to Kafka
        event = WorkflowRequestedEvent(
            event_id=uuid4(),
            request_id=record.request_id,
            correlation_id=record.correlation_id,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            payload=payload,
            attempt=1,
        )
        publisher.publish("workflow.requested", event)
        
    else:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
        logger.info("request_replayed", extra={"request_id": str(record.request_id)})
        request_count.labels(endpoint="/requests", status="replayed").inc()

    return RequestAccepted(
        request_id=record.request_id,
        correlation_id=record.correlation_id,
        status=record.status,
        created_at=record.created_at,
    )



@router.get("/{request_id}", response_model=RequestDetail)
def get_request(request_id: UUID, repository: RepositoryDep) -> RequestDetail:
    record = repository.get(request_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    return RequestDetail(
        request_id=record.request_id,
        correlation_id=record.correlation_id,
        status=record.status,
        request=record.payload,
        result=record.result,
        error_code=record.error_code,
        retry_count=record.retry_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

from pydantic import BaseModel
from opspilot_contracts import WorkflowStatus

class ApproveResponse(BaseModel):
    request_id: UUID
    status: WorkflowStatus

@router.post("/{request_id}/approve", response_model=ApproveResponse)
def approve_request(
    request_id: UUID,
    repository: RepositoryDep
) -> ApproveResponse:
    # Fetch the request
    detail = repository.get(request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if detail.status != WorkflowStatus.AWAITING_REVIEW:
        raise HTTPException(status_code=400, detail="Request is not awaiting review")
        
    # Transition to COMPLETED
    repository.transition(
        request_id=request_id,
        new_status=WorkflowStatus.COMPLETED,
        actor="human_reviewer",
        correlation_id=detail.correlation_id
    )
    
    return ApproveResponse(request_id=request_id, status=WorkflowStatus.COMPLETED)
