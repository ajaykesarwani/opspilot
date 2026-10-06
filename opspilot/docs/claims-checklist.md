# Portfolio Claims Checklist

Every claim below points at the code or test that backs it. If you can't point at evidence in an
interview, don't make the claim.

## Claims you can make

| Claim | Evidence |
|---|---|
| Event-driven services with FastAPI, Kafka and PostgreSQL | `services/api`, `services/worker`, `infra/docker-compose.yml` |
| Typed LangGraph workflow with bounded retries and a human approval gate | `packages/orchestration`; `test_graph_never_completes_without_human`; `services/api/tests/test_end_to_end.py` |
| Database-enforced idempotency (race-safe) | `UNIQUE` constraint in the migration; `test_concurrent_submissions_with_same_key_create_one_request[postgres]`; `scripts/load_test.py` |
| At-least-once processing with idempotent consumers | `KafkaEventConsumer` (commit after handling, seek-back on failure); `packages/messaging/tests`; `test_duplicate_delivery_is_idempotent` |
| Dead-letter queue with retry/backoff | `services/worker/main.py`; `test_retries_exhausted_dead_letters_request`, `test_malformed_message_is_dead_lettered` |
| RAG with threshold-based abstention | `VectorStore.search`; `test_abstains_on_unrelated_query`; `test_model_cannot_answer_when_evidence_is_insufficient` |
| Evaluation pipeline with a CI regression gate | `services/evaluation`; CI step "Evaluation regression gate" |
| Distributed tracing across API → Kafka → worker, plus Prometheus metrics | W3C context in Kafka headers (`producer.py`, `worker/main.py`); `/metrics/`, worker `:9100` |
| CI with real-database integration tests, frontend build and Docker image builds | `.github/workflows/ci.yml` |
| Wrote tests and measured coverage (~89% line coverage, 140+ tests) | `make test` |

Suggested wording: *"Built an event-driven AI workflow platform (FastAPI, Kafka, PostgreSQL,
LangGraph) with idempotent request handling, at-least-once processing with a dead-letter queue,
retrieval-threshold abstention, mandatory human approval, and a CI evaluation gate."*

## Claims you must NOT make

- **"Production deployed" / "scalable" / "highly available"**: local Docker Compose, single broker and database.
- **"Uses GPT/Claude/an LLM in production"**: only a deterministic mock provider exists.
- **"Semantic search"**: the offline embedder is lexical.
- **"Accuracy of X%"** without saying it is retrieval/abstention on 20 hand-written cases.
- **"Secure" / "enterprise-ready" / "GDPR compliant"**: no authentication, no rate limiting, no audit of PII handling.
- **"Exactly-once"**: delivery is at-least-once; correctness relies on idempotent handlers.
- **"Autonomous agent"**: it is deliberately not; a human must approve.
