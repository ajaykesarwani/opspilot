# Portfolio Claims Checklist

## ✅ Truthful Claims You CAN Make on a Résumé:
- **Architecture**: Designed and implemented an event-driven microservices architecture using FastAPI, Kafka, and PostgreSQL.
- **Workflow Orchestration**: Built deterministic operational automation using LangGraph with strict typed Pydantic state constraints.
- **Resiliency**: Implemented at-least-once message processing, dead-letter queues (DLQ), and database-enforced idempotency to prevent duplicate operations.
- **RAG Implementation**: Built a local Retrieval-Augmented Generation pipeline using ChromaDB with explicit thresholding for "Insufficient Evidence" abstention to prevent LLM hallucination.
- **Observability**: Instrumented the application with OpenTelemetry distributed tracing (Jaeger) and Prometheus metrics for actionable insights.
- **Evaluation-Driven**: Developed a local MLflow evaluation pipeline to measure RAG Recall@K and structured output validity against a golden dataset.
- **Human-in-the-Loop**: Engineered asynchronous workflows that pause execution for mandatory human review before applying final state changes.

## ❌ Unsupported Claims You MUST NOT Make:
- "Production Deployed" (The project is run locally via Docker Compose, not deployed to a live cloud environment like AWS/GCP).
- "GDPR Compliant" (No explicit data deletion pipelines, consent mechanisms, or PII scrubbing have been audited).
- "Enterprise-Ready" (Lacks robust API Gateway auth, distributed secret management like Vault, and Kubernetes orchestration).
- "Autonomous Decision-Making" (The system is explicitly designed to halt and require human approval, making it semi-autonomous).
- "High Availability / Scalable" (The local setup has single points of failure like a single Postgres container and single Kafka broker, and lacks replication).
