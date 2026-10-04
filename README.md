# OpsPilot: Observable AI Workflow Platform

OpsPilot is a local, portfolio-ready reference architecture demonstrating industry-standard engineering for AI and LLM orchestration. Rather than building unpredictable, opaque agents, OpsPilot enforces rigid orchestration, rigorous evaluation, and enterprise-grade observability to execute semi-autonomous operational workflows.

## 🚀 Key Features

*   **LangGraph Orchestration**: Deterministic workflows using typed Pydantic state to constrain AI behavior and enforce fallbacks.
*   **Event-Driven & Resilient**: Built on FastAPI, Apache Kafka, and PostgreSQL. Ensures at-least-once processing, database-enforced idempotency, and Dead-Letter Queue (DLQ) routing.
*   **Safe AI (Human-in-the-Loop)**: The system strictly abstains on insufficient evidence (RAG thresholding) and mandates human operator approval before finalizing any workflow.
*   **Evaluation-Driven Development**: Includes a local MLflow evaluation pipeline to test RAG Recall@K and structured output validity against a golden dataset to prevent regression.
*   **Deep Observability**: End-to-end OpenTelemetry distributed tracing (Jaeger) bridging FastAPI, Kafka, and LangGraph spans, alongside Prometheus operational metrics.
*   **No-Cost Local Execution**: Runs entirely via Docker Compose utilizing a Mock Embedder and Mock LLM for rapid, free prototyping.

## 🏗️ Architecture

```mermaid
flowchart LR
    UI[React Frontend] <--> |REST| API[FastAPI Service]
    API --> |Write (Idempotent)| DB[(PostgreSQL)]
    API --> |Publish| Kafka[Kafka Broker]
    Kafka --> |Consume| Worker[Worker Service]
    
    subgraph LangGraph Orchestration
        Worker --> |Invoke| LG[LangGraph]
        LG <--> RAG[Chroma RAG]
        LG <--> LLM[LLM Provider]
    end
    
    LG --> |Update State| DB
    
    subgraph Observability
        API -.-> |Traces/Metrics| OTEL[Jaeger / Prometheus]
        Worker -.-> |Traces/Metrics| OTEL
    end
```

## 🛠️ Local Setup

OpsPilot runs locally using Docker Compose and `uv` for Python dependency management.

### Prerequisites
- Docker & Docker Compose
- Node.js (for the frontend)
- [uv](https://github.com/astral-sh/uv) (for Python package management)

### 1. Start Infrastructure
Start PostgreSQL, Kafka, Jaeger, and Prometheus.
```bash
docker-compose up -d postgres kafka jaeger prometheus
```
Wait for services to be healthy, then run database migrations:
```bash
docker-compose up migrate
```

### 2. Start Services
Start the API and Worker in background:
```bash
docker-compose up -d api worker
```

### 3. Start Frontend
```bash
cd apps/frontend
npm install
npm run dev
```
Access the UI at `http://localhost:5173`.

## 🧪 Testing & Evaluation

### Unit & Integration Tests
Run tests locally using `uv`:
```bash
uv run pytest
```

### Evaluation Pipeline (MLflow)
Evaluate the RAG pipeline against the golden dataset:
```bash
uv run python services/evaluation/opspilot_evaluation/run_eval.py
```
Check the generated `data/knowledge_base/eval_report.md` and local `mlruns.db`.

### Load Testing
A script is provided to verify idempotency and queue resilience:
```bash
uv run python scripts/load_test.py
```

## 🔍 Observability
- **Jaeger (Traces)**: `http://localhost:16686`
- **Prometheus (Metrics)**: `http://localhost:9090`
- **API Metrics**: `http://localhost:8000/metrics`

## 📖 Documentation
- [Runbook & Troubleshooting](docs/runbook.md)
- [Threat Model](docs/threat-model.md)
- [Architecture Decision Records (ADRs)](docs/adr/)
- [Demo Script](docs/demo-script.md)
- [Claims Checklist](docs/claims-checklist.md)

## ⚠️ Known Limitations
- **Local Only**: Not configured for Kubernetes, cloud deployments, or multi-node high availability.
- **Mock LLM**: The current version relies on a deterministic Mock LLM for zero-cost execution. To use OpenAI/Anthropic, the `LLMProvider` interface in `opspilot_orchestration/llm.py` must be implemented.
- **Authentication**: The UI lacks actual authentication flows and relies on a mock "demo user".
- **Chroma**: Runs ephemerally in-memory for the worker; production would migrate to `pgvector` or persistent Chroma storage.
