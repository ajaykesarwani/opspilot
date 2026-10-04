import logging
from typing import Dict, Any, cast

from opspilot_orchestration.state import WorkflowState, Recommendation
from opspilot_orchestration.llm import get_llm_provider
from opspilot_rag.store import VectorStore, InsufficientEvidenceError

logger = logging.getLogger(__name__)

from opspilot_common.telemetry import get_tracer, retrieval_duration, provider_failures
import time

tracer = get_tracer(__name__)

class WorkflowNodes:
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.llm = get_llm_provider()

    def validate_request(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("validate_request") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Validating request {state.request_id}")
            # Basic validation logic
            if not state.request.subject or not state.request.body:
                span.set_attribute("is_valid", False)
                return {"is_valid": False, "error": "Subject and body cannot be empty"}
            span.set_attribute("is_valid", True)
            return {"is_valid": True}

    def classify_request(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("classify_request") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Classifying request {state.request_id}")
            # Mock classification
            return {"classification": "general_operation"}

    def retrieve_context(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("retrieve_context") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Retrieving context for {state.request_id}")
            query = f"{state.request.subject} {state.request.body}"
            
            start = time.time()
            try:
                chunks = self.vector_store.search(query=query, top_k=3, min_score=0.1)
                retrieval_duration.observe(time.time() - start)
                retrieved_chunks = [c.text for c in chunks]
                span.set_attribute("retrieved_chunks_count", len(retrieved_chunks))
                return {"retrieved_chunks": retrieved_chunks, "insufficient_evidence": False}
            except InsufficientEvidenceError:
                retrieval_duration.observe(time.time() - start)
                span.set_attribute("insufficient_evidence", True)
                return {"retrieved_chunks": [], "insufficient_evidence": True}
            except Exception as e:
                retrieval_duration.observe(time.time() - start)
                span.record_exception(e)
                logger.error(f"Error in retrieve_context: {e}")
                return {"retrieved_chunks": [], "insufficient_evidence": True}

    def assess_evidence(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("assess_evidence") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Assessing evidence for {state.request_id}")
            return {}

    def draft_recommendation(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("draft_recommendation") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Drafting recommendation for {state.request_id}")
            prompt = f"""
            INSUFFICIENT_EVIDENCE: {state.insufficient_evidence}
            Context: {state.retrieved_chunks}
            Subject: {state.request.subject}
            Body: {state.request.body}
            """
            try:
                rec = self.llm.generate_structured(prompt, Recommendation)
                return {"recommendation": rec}
            except Exception as e:
                provider_failures.inc()
                span.record_exception(e)
                logger.error(f"Provider failed: {e}")
                return {"error": str(e)}

    def validate_structured_output(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("validate_structured_output") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Validating output for {state.request_id}")
            if state.error or not state.recommendation:
                return {"validation_retries": state.validation_retries + 1}
            return {}

    def await_human_review(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("await_human_review") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Awaiting human review for {state.request_id}")
            return {"final_status": "AWAITING_REVIEW"}

    def complete_or_fail(self, state: WorkflowState) -> Dict[str, Any]:
        with tracer.start_as_current_span("complete_or_fail") as span:
            span.set_attribute("request_id", state.request_id)
            logger.info(f"Completing or failing {state.request_id}")
            if not state.is_valid or state.validation_retries >= state.max_retries or state.error:
                span.set_attribute("final_status", "FAILED")
                return {"final_status": "FAILED"}
            
            if state.final_status == "AWAITING_REVIEW":
                span.set_attribute("final_status", "COMPLETED")
                return {"final_status": "COMPLETED"}
            
            span.set_attribute("final_status", "FAILED")
            return {"final_status": "FAILED"}
