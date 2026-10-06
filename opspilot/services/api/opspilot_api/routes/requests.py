import logging
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel

from opspilot_api.deps import PublisherDep, RepositoryDep
from opspilot_api.idempotency import payload_fingerprint
from opspilot_common.correlation import get_correlation_id, new_correlation_id
from opspilot_common.telemetry import request_count
from opspilot_contracts import (
    InvalidTransitionError,
    OperationalRequestCreate,
    RequestAccepted,
    RequestDetail,
    Topics,
    WorkflowRequestedEvent,
    WorkflowRequestedPayload,
    WorkflowStatus,
)
from opspilot_messaging import PublishError
from opspilot_persistence.repositories.base import (
    IdempotencyConflictError,
    NewRequest,
    RequestNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])
TOPICS = Topics()

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


class ApproveResponse(BaseModel):
    request_id: UUID
    status: WorkflowStatus


# Sync handlers: SQLAlchemy and the Kafka producer block, so FastAPI runs them in its threadpool.
@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=RequestAccepted)
def create_request(
    payload: OperationalRequestCreate,
    repository: RepositoryDep,
    publisher: PublisherDep,
    response: Response,
    idempotency_key: IdempotencyKeyHeader = None,
) -> RequestAccepted:
    """Accept an operational request; processing is asynchronous.

    Delivery guarantee: the request is persisted (VALIDATED), the event is published and
    acknowledged by the broker, and only then is the request marked QUEUED. If publishing fails
    the API answers 503 and the request stays VALIDATED; retrying with the same Idempotency-Key
    re-publishes it. The worker is idempotent, so a duplicate event is harmless.

    A replayed Idempotency-Key with the same payload returns 200 and the original request; with
    a different payload it returns 409.
    """
    correlation_id = get_correlation_id() or new_correlation_id()
    new = NewRequest(
        request_id=uuid4(),
        correlation_id=correlation_id,
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
    if record.status == WorkflowStatus.VALIDATED:  # new, or an earlier publish never succeeded
        event = WorkflowRequestedEvent(
            request_id=record.request_id,
            correlation_id=record.correlation_id,
            payload=WorkflowRequestedPayload(priority=record.payload.priority),
        )
        try:
            publisher.publish(TOPICS.requested, event)
        except PublishError:
            logger.exception("publish_failed", extra={"request_id": str(record.request_id)})
            request_count.labels(endpoint="/requests", status="publish_failed").inc()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not queue the request. Retry with the same Idempotency-Key.",
                headers={"Retry-After": "5"},
            ) from None
        record = repository.transition(
            record.request_id,
            WorkflowStatus.QUEUED,
            actor="api",
            correlation_id=record.correlation_id,
        )

    if outcome.created:
        logger.info(
            "request_accepted",
            extra={"request_id": str(record.request_id), "priority": payload.priority.value},
        )
        request_count.labels(endpoint="/requests", status="accepted").inc()
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


@router.post("/{request_id}/approve", response_model=ApproveResponse)
def approve_request(request_id: UUID, repository: RepositoryDep) -> ApproveResponse:
    """Human approval: AWAITING_REVIEW -> COMPLETED (the only way a request completes)."""
    record = repository.get(request_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    try:
        # The repository re-checks the state under a row lock, so concurrent approvals are safe.
        repository.transition(
            request_id,
            WorkflowStatus.COMPLETED,
            actor="human_reviewer",  # no authentication yet (see README: Known Limitations)
            correlation_id=record.correlation_id,
        )
    except RequestNotFoundError:
        raise HTTPException(status_code=404, detail="Request not found.") from None
    except InvalidTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Request is not awaiting review."
        ) from None
    return ApproveResponse(request_id=request_id, status=WorkflowStatus.COMPLETED)
