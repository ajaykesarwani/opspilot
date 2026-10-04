# ADR 0001: Use Kafka and At-Least-Once Processing

## Context
OpsPilot requires reliable background processing of operational workflows. A workflow can be complex, involving vector store retrieval, LLM generation, and database updates. Synchronous processing blocks the API and is prone to timeout errors, especially during LLM degradation.

## Decision
We chose Apache Kafka to decouple the API from background processing. We implement an **at-least-once** delivery guarantee.

## Rationale
- **Resilience**: If the worker crashes or the LLM times out, the event is re-delivered or dead-lettered, ensuring no lost work.
- **Scalability**: Decoupling allows scaling API and workers independently.
- **Idempotency Requirement**: Because Kafka uses at-least-once delivery, workers must check the workflow state in PostgreSQL (idempotency checks) before initiating processing.

## Consequences
- Requires Kafka infrastructure, increasing local and production complexity.
- Requires strict idempotency logic in the database (e.g., using `FOR UPDATE` and specific status transitions).
