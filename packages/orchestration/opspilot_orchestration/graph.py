from typing import Literal
from langgraph.graph import StateGraph, END
from opspilot_orchestration.state import WorkflowState
from opspilot_orchestration.nodes import WorkflowNodes
from opspilot_rag.store import VectorStore

def should_continue_after_validation(state: WorkflowState) -> Literal["classify_request", "complete_or_fail"]:
    if state.is_valid:
        return "classify_request"
    return "complete_or_fail"

def should_retry_after_structured_validation(state: WorkflowState) -> Literal["draft_recommendation", "complete_or_fail", "await_human_review"]:
    if not state.recommendation or state.error:
        if state.validation_retries < state.max_retries:
            return "draft_recommendation"
        return "complete_or_fail"
    return "await_human_review"

def create_workflow(vector_store: VectorStore):
    nodes = WorkflowNodes(vector_store)
    
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("validate_request", nodes.validate_request)
    workflow.add_node("classify_request", nodes.classify_request)
    workflow.add_node("retrieve_context", nodes.retrieve_context)
    workflow.add_node("assess_evidence", nodes.assess_evidence)
    workflow.add_node("draft_recommendation", nodes.draft_recommendation)
    workflow.add_node("validate_structured_output", nodes.validate_structured_output)
    workflow.add_node("await_human_review", nodes.await_human_review)
    workflow.add_node("complete_or_fail", nodes.complete_or_fail)
    
    # Define edges
    workflow.set_entry_point("validate_request")
    
    workflow.add_conditional_edges(
        "validate_request",
        should_continue_after_validation,
        {
            "classify_request": "classify_request",
            "complete_or_fail": "complete_or_fail"
        }
    )
    
    workflow.add_edge("classify_request", "retrieve_context")
    workflow.add_edge("retrieve_context", "assess_evidence")
    workflow.add_edge("assess_evidence", "draft_recommendation")
    workflow.add_edge("draft_recommendation", "validate_structured_output")
    
    workflow.add_conditional_edges(
        "validate_structured_output",
        should_retry_after_structured_validation,
        {
            "draft_recommendation": "draft_recommendation",
            "complete_or_fail": "complete_or_fail",
            "await_human_review": "await_human_review"
        }
    )
    
    # Add an interruption point before completing.
    # We just link await_human_review to END, or we link it to complete_or_fail and interrupt before it.
    # Let's link await_human_review to complete_or_fail, but we'll set a breakpoint before complete_or_fail.
    workflow.add_edge("await_human_review", "complete_or_fail")
    workflow.add_edge("complete_or_fail", END)
    
    # Compile with memory/checkpointer in real usage, but here we can just compile it.
    # To support interruption, we would need a checkpointer. 
    # For now, compiling it so it can be invoked.
    return workflow.compile(interrupt_before=["complete_or_fail"])
