# OpsPilot Runbook

Every log line, trace and audit row carries the request's `correlation_id`. Start there.

## Find a request and its history
```bash
curl localhost:8000/api/v1/requests/<request_id>            # status, result, error_code, retry_count
docker compose -f infra/docker-compose.yml exec postgres psql -U opspilot -c \
  "select to_status, actor, created_at from audit_events where request_id='<request_id>' order by id"
```
The audit trail shows who moved the request through each state (`api`, `worker`, `human_reviewer`).

## 1. A request is stuck
| Status | Meaning | Action |
|---|---|---|
| `VALIDATED` | stored but the broker never acknowledged | client retries with the same `Idempotency-Key`; if no key was used the row is orphaned (known limitation) |
| `QUEUED` | published, worker has not picked it up | `docker compose logs worker`; is the worker up and consuming `workflow.requested`? |
| `PROCESSING` | a worker is running it, or died mid-flight | redelivery recovers it automatically on restart (`retry_count` increments) |
| `AWAITING_REVIEW` | working as designed: a human must approve | `POST /api/v1/requests/<id>/approve` |

## 2. A workflow failed
`FAILED` + `error_code=WORKFLOW_FAILED`: the graph ended in failure (provider errors or invalid
structured output after retries). `result.error` has the message. In Jaeger, find the trace by
`request_id` and look at `draft_recommendation` / `validate_structured_output`. Metric:
`opspilot_workflow_failure{reason="graph_failed"}`, `opspilot_provider_failures`.

## 3. Messages in the dead-letter topic
`DEAD_LETTERED` requests and everything on `workflow.dlq`:
```bash
docker compose -f infra/docker-compose.yml exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 --topic workflow.dlq --from-beginning
```
Each event has `payload.reason`: `MALFORMED_MESSAGE`, `REQUEST_NOT_FOUND`, `INVALID_STATE`,
`RETRIES_EXHAUSTED` or `UNEXPECTED_ERROR`, plus source partition/offset and the original
message. Use the `correlation_id` to find the worker stack trace. After fixing the cause,
republish the original message to `workflow.requested`; the worker is idempotent. Metric:
`opspilot_dlq_messages{reason=...}`.

## 4. Duplicate processing suspected
Duplicates are expected under at-least-once delivery and are ignored: the worker logs
`duplicate_event_ignored` for requests already past `QUEUED`. `idempotency_conflict` in the API
log means a client reused a key with a different payload (409).

## 5. Slow processing
`opspilot_workflow_duration_seconds` and `opspilot_retrieval_duration_seconds` (Prometheus,
`localhost:9090`). In Jaeger the longest span is normally the LLM call (`draft_recommendation`).

## 6. Evaluation regression in CI
`make eval` prints which metric dropped below baseline. Inspect `reports/eval_report.md` for the
per-case table. If the change is intentional (new threshold, embedder, dataset), run
`uv run python services/evaluation/opspilot_evaluation/run_eval.py --update-baseline` and commit the new baseline with an explanation.
