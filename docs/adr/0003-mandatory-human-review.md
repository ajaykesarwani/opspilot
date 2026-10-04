# ADR 0003: Mandatory Human Review

## Context
OpsPilot outputs operational recommendations that might modify infrastructure state or sensitive environments. 

## Decision
All operational workflows must halt at an `AWAITING_REVIEW` state. The graph explicitly requires a `/approve` HTTP callback to transition to `COMPLETED`. No agent is allowed to make autonomous real-world side effects.

## Rationale
- **Safety**: LLMs, even with RAG, can hallucinate or draw incorrect conclusions from correct context.
- **Accountability**: An operator must take responsibility for the final action.
- **Evaluation Loop**: The human-in-the-loop (HITL) step serves as a critical data collection point to evaluate model correctness in a future iteration.

## Consequences
- Workflows are entirely asynchronous.
- The UI must support polling or WebSocket connections to surface the review checkpoint to the operator.
