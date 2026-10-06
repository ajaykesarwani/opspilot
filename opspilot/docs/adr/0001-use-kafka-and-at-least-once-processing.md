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

## Implementation notes
- **Producer side:** the API persists the request (`VALIDATED`), publishes with `acks=all` and
  idempotence enabled, waits for the broker acknowledgement, and only then marks it `QUEUED`. A
  publish failure returns `503`; a retry with the same `Idempotency-Key` republishes.
- **Consumer side:** offsets are committed only after the handler returns. If it raises (for
  example the database is down) the consumer seeks back and the message is redelivered.
- **Handler:** idempotent via persisted status. Already-handled requests are skipped, a request
  stuck in `PROCESSING` after a worker crash re-enters through the `PROCESSING -> QUEUED` retry
  edge, workflow failures are retried with exponential backoff up to `max_attempts`, and
  anything unprocessable is published to `workflow.dlq` (and the request marked `DEAD_LETTERED`).
- **Not implemented:** a transactional outbox. It would remove the remaining gap where a request
  sent without an `Idempotency-Key` is orphaned in `VALIDATED` after a broker outage.
