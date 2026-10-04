# OpsPilot Runbook

## 1. Investigating a Failed Workflow

**Symptom**: Workflow metric `opspilot_workflow_failure` is spiking, or a user reports a failed request.
**Steps**:
1. Open the tracing backend (e.g., Jaeger) and search for traces where `final_status == "FAILED"`.
2. Look for the `request_id` or `correlation_id` in the trace tags.
3. Review the spans to find the exact node that failed (e.g., `draft_recommendation` or `validate_structured_output`).
4. Check standard logs for the `correlation_id` to read the specific exception message.
5. If the node `validate_structured_output` failed multiple times, the LLM output is violating the schema.

## 2. Investigating a Slow Workflow

**Symptom**: `opspilot_workflow_duration_seconds` metric shows high latency.
**Steps**:
1. Check the `opspilot_retrieval_duration_seconds` metric. If retrieval is slow, the vector store (Chroma) might be bottlenecked.
2. If retrieval is normal, open the tracing backend and filter for slow traces.
3. Inspect the waterfall view. Usually, `draft_recommendation` (LLM call) takes the most time. If it's taking abnormally long, check if `opspilot_provider_failures` is triggering retries due to timeouts.

## 3. Investigating a Duplicate Kafka Event

**Symptom**: You notice workflows processing multiple times for the same payload.
**Steps**:
1. The system uses the `Idempotency-Key` header and Payload Fingerprint to prevent duplicate DB writes.
2. Check the logs for `idempotency_conflict`. If this is happening, someone is reusing an idempotency key with different payloads.
3. For Kafka duplicates, the worker checks the current state of the request in Postgres (`status` transition constraint). If the transition fails because it's already `PROCESSING` or `COMPLETED`, the worker ignores it.
4. Verify the worker consumer logs. Search for `correlation_id` to see if the message was dropped as a duplicate state transition.

## 4. Investigating a DLQ (Dead Letter Queue) Event

**Symptom**: Messages are accumulating in the `workflow.dlq` topic.
**Steps**:
1. Inspect the DLQ messages. They contain the original payload and the `error_code`/`attempt` count.
2. A message goes to DLQ if it consistently fails processing (e.g. malformed JSON, or transient error max retries exceeded).
3. Extract the `correlation_id` from the DLQ event.
4. Query the logs for this `correlation_id` to find the stack trace that caused the worker to repeatedly fail.
5. Fix the bug, then use a script to republish the DLQ messages back to `workflow.requested` for reprocessing.
