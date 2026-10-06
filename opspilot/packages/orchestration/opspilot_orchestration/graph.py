from typing import Literal

from langgraph.graph import END, StateGraph

from opspilot_orchestration.llm import LLMProvider
from opspilot_orchestration.nodes import WorkflowNodes
from opspilot_orchestration.state import WorkflowState
from opspilot_rag.store import VectorStore


def route_after_validation(state: WorkflowState) -> Literal["classify_request", "mark_failed"]:
    return "classify_request" if state.is_valid else "mark_failed"


def route_after_output_validation(
    state: WorkflowState,
) -> Literal["draft_recommendation", "mark_failed", "await_human_review"]:
    if state.recommendation is None or state.error:
        return (
            "draft_recommendation"
            if state.validation_retries < state.max_retries
            else "mark_failed"
        )
    return "await_human_review"


def create_workflow(vector_store: VectorStore, llm: LLMProvider | None = None):
    """Compile the workflow.

    validate -> classify -> retrieve -> draft -> validate output -(retry)-> ... -> review | failed

    The graph is stateless and always terminates: human approval is a separate, persisted
    transition (AWAITING_REVIEW -> COMPLETED) performed through the API (ADR 0003).
    """
    nodes = WorkflowNodes(vector_store, llm)
    graph = StateGraph(WorkflowState)
    graph.add_node("validate_request", nodes.validate_request)
    graph.add_node("classify_request", nodes.classify_request)
    graph.add_node("retrieve_context", nodes.retrieve_context)
    graph.add_node("draft_recommendation", nodes.draft_recommendation)
    graph.add_node("validate_structured_output", nodes.validate_structured_output)
    graph.add_node("await_human_review", nodes.await_human_review)
    graph.add_node("mark_failed", nodes.mark_failed)

    graph.set_entry_point("validate_request")
    graph.add_conditional_edges("validate_request", route_after_validation)
    graph.add_edge("classify_request", "retrieve_context")
    graph.add_edge("retrieve_context", "draft_recommendation")
    graph.add_edge("draft_recommendation", "validate_structured_output")
    graph.add_conditional_edges("validate_structured_output", route_after_output_validation)
    graph.add_edge("await_human_review", END)
    graph.add_edge("mark_failed", END)
    return graph.compile()
