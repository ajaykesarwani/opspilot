# ADR 0002: Use LangGraph and Typed Workflow State

## Context
OpsPilot workflows require multiple deterministic (validation) and non-deterministic (LLM) steps with cyclic logic (retrying on invalid structured output).

## Decision
We adopted LangGraph to model the orchestration using an explicitly defined, strict Pydantic `WorkflowState`.

## Rationale
- **Control over Automation**: Standard LLM agent frameworks (like generic ReAct agents) are too unpredictable for operational automation. LangGraph allows us to define rigid nodes and edges.
- **Typed State**: Using Pydantic forces type constraints across the graph, mitigating common hallucination-driven errors.
- **Cycles**: Simple sequential pipelines cannot handle fallback loops (e.g., retrying validation). LangGraph supports cyclic edges inherently.

## Consequences
- Requires adapting typical Python dict-based state into Pydantic abstractions.
- Developers must understand graph orchestration theory rather than just prompt engineering.
