"""Kafka worker: consumes workflow.requested, runs the LangGraph workflow, records the result.

Delivery semantics: at-least-once. An offset is committed only after `handle_message` returns;
the handler is idempotent (duplicates are detected from the persisted status), retries workflow
failures with backoff, and dead-letters anything it cannot process instead of dropping it.
"""

import logging
import signal
import time
from collections.abc import Callable
from typing import Any

from opentelemetry import propagate, trace
from prometheus_client import start_http_server
from pydantic import ValidationError

from opspilot_common.correlation import set_correlation_id
from opspilot_common.logging import configure_logging
from opspilot_common.telemetry import (
    dlq_messages,
    get_tracer,
    setup_telemetry,
    workflow_duration,
    workflow_failure,
    workflow_success,
)
from opspilot_contracts import (
    DeadLetterEvent,
    DeadLetterPayload,
    DeadLetterReason,
    InvalidTransitionError,
    Topics,
    WorkflowCompletedEvent,
    WorkflowCompletedPayload,
    WorkflowFailedEvent,
    WorkflowFailedPayload,
    WorkflowRequestedEvent,
    WorkflowStatus,
)
from opspilot_messaging import (
    EventPublisher,
    KafkaEventConsumer,
    KafkaEventPublisher,
    Message,
    PublishError,
    ensure_topics,
)
from opspilot_orchestration import WorkflowState, create_workflow
from opspilot_persistence.db.engine import create_db_engine
from opspilot_persistence.repositories.base import RequestRecord, RequestRepository
from opspilot_persistence.repositories.postgres import PostgresRequestRepository
from opspilot_rag import MockEmbedder, VectorStore, load_knowledge_base
from opspilot_worker.settings import Settings

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
TOPICS = Topics()

_ALREADY_HANDLED = frozenset(
    {
        WorkflowStatus.AWAITING_REVIEW,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.FAILED,
        WorkflowStatus.DEAD_LETTERED,
    }
)


class WorkerService:
    def __init__(
        self,
        settings: Settings,
        repository: RequestRepository,
        publisher: EventPublisher,
        workflow: Any,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.publisher = publisher
        self.workflow = workflow
        self._sleep = sleep
        self.consumer: KafkaEventConsumer | None = None

    @classmethod
    def build(cls, settings: Settings) -> "WorkerService":
        setup_telemetry("opspilot_worker")
        repository = PostgresRequestRepository(create_db_engine(settings.database_url))
        store = VectorStore(MockEmbedder())  # swap for a real embedder when mock_mode=False
        load_knowledge_base(store, settings.knowledge_base_dir)
        return cls(
            settings,
            repository,
            KafkaEventPublisher(settings.kafka_bootstrap_servers),
            create_workflow(store),
        )

    # ------------------------------------------------------------------ message handling

    def handle_message(self, message: Message) -> None:
        """Process one message. Returns normally when it is safe to commit the offset; raises
        only for transient infrastructure errors (the consumer then redelivers)."""
        context = propagate.extract(message.headers)
        with tracer.start_as_current_span(
            "workflow.requested process", context=context, kind=trace.SpanKind.CONSUMER
        ):
            try:
                event = WorkflowRequestedEvent.model_validate_json(message.value)
            except ValidationError as exc:
                self._dead_letter(
                    DeadLetterReason.MALFORMED_MESSAGE,
                    f"Invalid event: {exc.error_count()} errors",
                    message=message,
                )
                return
            set_correlation_id(event.correlation_id)
            self._process(event, message)

    def _process(self, event: WorkflowRequestedEvent, message: Message) -> None:
        record = self.repository.get(event.request_id)
        if record is None:
            self._dead_letter(
                DeadLetterReason.REQUEST_NOT_FOUND, "Request does not exist", event, message
            )
            return
        if record.status in _ALREADY_HANDLED:
            logger.info("duplicate_event_ignored", extra={"status": record.status.value})
            return

        record = self._await_queued(record)
        if record.status == WorkflowStatus.VALIDATED:
            self._dead_letter(
                DeadLetterReason.INVALID_STATE,
                "Request was never marked QUEUED by the API",
                event,
                message,
            )
            return
        if record.status == WorkflowStatus.PROCESSING:
            # A previous worker died mid-flight. Re-enter via the retry edge.
            record = self.repository.transition(
                event.request_id,
                WorkflowStatus.QUEUED,
                actor="worker",
                correlation_id=event.correlation_id,
                increment_retry=True,
            )

        attempt = record.retry_count + 1
        while True:
            if attempt > self.settings.max_attempts:
                self._dead_letter(
                    DeadLetterReason.RETRIES_EXHAUSTED, "Retries exhausted", event, message
                )
                return
            try:
                self.repository.transition(
                    event.request_id,
                    WorkflowStatus.PROCESSING,
                    actor="worker",
                    correlation_id=event.correlation_id,
                )
            except InvalidTransitionError:
                logger.info("concurrent_processing_detected")
                return
            try:
                final = self._run_workflow(record, event)
            except Exception as exc:
                workflow_failure.labels(reason="exception").inc()
                logger.exception("workflow_attempt_failed", extra={"attempt": attempt})
                if attempt >= self.settings.max_attempts:
                    self._dead_letter(DeadLetterReason.RETRIES_EXHAUSTED, str(exc), event, message)
                    return
                self.repository.transition(
                    event.request_id,
                    WorkflowStatus.QUEUED,
                    actor="worker",
                    correlation_id=event.correlation_id,
                    increment_retry=True,
                )
                self._sleep(self.settings.retry_backoff_seconds * 2 ** (attempt - 1))
                attempt += 1
                continue
            self._finish(event, final, attempt)
            return

    def _await_queued(self, record: RequestRecord) -> RequestRecord:
        """The event can reach us before the API's VALIDATED -> QUEUED update commits."""
        for _ in range(self.settings.queued_wait_polls):
            if record.status != WorkflowStatus.VALIDATED:
                break
            self._sleep(self.settings.queued_wait_interval_seconds)
            refreshed = self.repository.get(record.request_id)
            if refreshed is None:
                break
            record = refreshed
        return record

    def _run_workflow(self, record: RequestRecord, event: WorkflowRequestedEvent) -> dict[str, Any]:
        state = WorkflowState(
            request_id=str(event.request_id),
            correlation_id=event.correlation_id,
            request=record.payload,
        )
        started = time.perf_counter()
        try:
            return self.workflow.invoke(state)
        finally:
            workflow_duration.observe(time.perf_counter() - started)

    def _finish(self, event: WorkflowRequestedEvent, final: dict[str, Any], attempt: int) -> None:
        recommendation = final.get("recommendation")
        if final.get("final_status") == "AWAITING_REVIEW" and recommendation is not None:
            self.repository.transition(
                event.request_id,
                WorkflowStatus.AWAITING_REVIEW,
                actor="worker",
                correlation_id=event.correlation_id,
                result={
                    "recommendation": recommendation.model_dump(),
                    "classification": final.get("classification"),
                    "insufficient_evidence": final.get("insufficient_evidence", False),
                },
            )
            workflow_success.inc()
            self._emit(
                TOPICS.completed,
                WorkflowCompletedEvent(
                    request_id=event.request_id,
                    correlation_id=event.correlation_id,
                    attempt=attempt,
                    payload=WorkflowCompletedPayload(
                        status=WorkflowStatus.AWAITING_REVIEW, processor=self.settings.service_name
                    ),
                ),
            )
            return

        message = str(final.get("error") or "Workflow failed")[:500]
        self.repository.transition(
            event.request_id,
            WorkflowStatus.FAILED,
            actor="worker",
            correlation_id=event.correlation_id,
            error_code="WORKFLOW_FAILED",
            result={"error": message},
        )
        workflow_failure.labels(reason="graph_failed").inc()
        self._emit(
            TOPICS.failed,
            WorkflowFailedEvent(
                request_id=event.request_id,
                correlation_id=event.correlation_id,
                attempt=attempt,
                payload=WorkflowFailedPayload(
                    final_status=WorkflowStatus.FAILED,
                    error_code="WORKFLOW_FAILED",
                    error_message=message,
                ),
            ),
        )

    # ------------------------------------------------------------------ publishing helpers

    def _emit(self, topic: str, event: Any) -> None:
        """Best-effort notification. The database already holds the truth; a lost notification
        must not cause a completed request to be reprocessed."""
        try:
            self.publisher.publish(topic, event)
        except PublishError:
            logger.warning("notification_publish_failed", extra={"topic": topic})

    def _dead_letter(
        self,
        reason: DeadLetterReason,
        error_message: str,
        event: WorkflowRequestedEvent | None = None,
        message: Message | None = None,
    ) -> None:
        """Park an unprocessable message. Publishing to the DLQ must succeed (a failure raises,
        so the offset is not committed and the message is redelivered)."""
        error_message = error_message[:500]
        if event is not None:
            record = self.repository.get(event.request_id)
            if record is not None and record.status not in _ALREADY_HANDLED:
                try:
                    self.repository.transition(
                        event.request_id,
                        WorkflowStatus.DEAD_LETTERED,
                        actor="worker",
                        correlation_id=event.correlation_id,
                        error_code=reason.value,
                    )
                except InvalidTransitionError:
                    # e.g. VALIDATED -> DEAD_LETTERED is not allowed; the DLQ record still exists.
                    logger.warning("dead_letter_status_not_updated", extra={"reason": reason.value})
        original = message.value.decode("utf-8", errors="replace")[:8192] if message else None
        self.publisher.publish(
            TOPICS.dlq,
            DeadLetterEvent(
                request_id=event.request_id if event else None,
                correlation_id=event.correlation_id if event else None,
                payload=DeadLetterPayload(
                    reason=reason,
                    error_message=error_message,
                    source_topic=message.topic if message else TOPICS.requested,
                    source_partition=message.partition if message else None,
                    source_offset=message.offset if message else None,
                    original_message=original,
                ),
            ),
        )
        dlq_messages.labels(reason=reason.value).inc()
        logger.error("message_dead_lettered", extra={"reason": reason.value})

    # ------------------------------------------------------------------ lifecycle

    def run(self) -> None:
        configure_logging(self.settings.service_name, self.settings.log_level)
        ensure_topics(self.settings.kafka_bootstrap_servers, TOPICS.all())
        start_http_server(self.settings.metrics_port)
        self.consumer = KafkaEventConsumer(
            self.settings.kafka_bootstrap_servers,
            self.settings.consumer_group_id,
            [TOPICS.requested],
        )

        def shutdown(_signo: int, _frame: Any) -> None:
            logger.info("worker_stopping")
            if self.consumer:
                self.consumer.stop()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        logger.info("worker_started")
        try:
            self.consumer.start(self.handle_message)
        finally:
            self.publisher.flush()


def main() -> None:
    settings = Settings()
    configure_logging(settings.service_name, settings.log_level)
    WorkerService.build(settings).run()


if __name__ == "__main__":
    main()
