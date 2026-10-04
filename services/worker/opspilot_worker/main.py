import json
import logging
import signal
import sys
import time
from typing import Any

from opspilot_worker.settings import Settings
from opspilot_common.logging import configure_logging
from opspilot_contracts.events import WorkflowRequestedEvent
from opspilot_contracts import WorkflowStatus
from opspilot_messaging import KafkaEventConsumer
from opspilot_persistence.repositories.postgres import PostgresRequestRepository
from opspilot_persistence.db.engine import create_db_engine
from opspilot_common.telemetry import setup_telemetry, workflow_success, workflow_failure, workflow_duration
from opentelemetry.instrumentation.confluent_kafka import ConfluentKafkaInstrumentor
import time

logger = logging.getLogger(__name__)

class WorkerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.consumer = None
        self.repository = None
        
        setup_telemetry("opspilot_worker")
        ConfluentKafkaInstrumentor().instrument()

        if not self.settings.mock_mode:
            engine = create_db_engine(self.settings.database_url)
            self.repository = PostgresRequestRepository(engine)
            
        from opspilot_rag import VectorStore, MockEmbedder
        # We use MockEmbedder consistently
        self.vector_store = VectorStore(MockEmbedder())
        
        from opspilot_orchestration import create_workflow
        self.workflow = create_workflow(self.vector_store)

    def handle_message(self, topic: str, value: bytes) -> None:
        try:
            payload = value.decode("utf-8")
            data = json.loads(payload)
            event = WorkflowRequestedEvent(**data)
            
            logger.info("processing_workflow", extra={"request_id": str(event.request_id)})
            
            if self.repository:
                self.repository.transition(
                    request_id=event.request_id, 
                    new_status=WorkflowStatus.PROCESSING,
                    actor="worker",
                    correlation_id=event.correlation_id
                )
                
                request_detail = self.repository.get(event.request_id)
                if not request_detail:
                    logger.error(f"Request {event.request_id} not found in DB")
                    return
                    
                # Run LangGraph workflow
                from opspilot_orchestration import WorkflowState
                from opspilot_contracts.requests import OperationalRequestCreate
                
                initial_state = WorkflowState(
                    request_id=str(event.request_id),
                    correlation_id=event.correlation_id,
                    request=OperationalRequestCreate(
                        subject=request_detail.subject,
                        body=request_detail.body,
                        requester=request_detail.requester,
                        priority=request_detail.priority
                    )
                )
                
                start_time = time.time()
                # Invoke graph
                final_state = self.workflow.invoke(initial_state)
                duration = time.time() - start_time
                workflow_duration.observe(duration)
                
                # Retrieve final state attributes
                final_status = getattr(final_state, "final_status", None)
                if isinstance(final_state, dict):
                    final_status = final_state.get("final_status")
                    
                target_status = WorkflowStatus.AWAITING_REVIEW if final_status == "AWAITING_REVIEW" else WorkflowStatus.FAILED
                
                self.repository.transition(
                    request_id=event.request_id, 
                    new_status=target_status,
                    actor="worker",
                    correlation_id=event.correlation_id
                )
                
                if target_status == WorkflowStatus.FAILED:
                    workflow_failure.labels(reason="graph_failed").inc()
                else:
                    workflow_success.inc()
                
            logger.info("workflow_processed", extra={"request_id": str(event.request_id)})
            
        except Exception as e:
            workflow_failure.labels(reason="exception").inc()
            logger.exception("failed_to_process_message", extra={"error": str(e)})

    def run(self):
        configure_logging(self.settings.service_name, self.settings.log_level)
        logger.info("worker_starting")

        self.consumer = KafkaEventConsumer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            group_id=self.settings.consumer_group_id,
            topics=["workflow.requested"]
        )

        def sigterm_handler(_signo: int, _stack_frame: Any) -> None:
            logger.info("worker_stopping")
            self.consumer.stop()

        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGINT, sigterm_handler)

        self.consumer.start(self.handle_message)
        logger.info("worker_stopped")

if __name__ == "__main__":
    settings = Settings()
    worker = WorkerService(settings)
    worker.run()
