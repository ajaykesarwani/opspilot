# OpsPilot Threat Model

This document outlines the security risks associated with the AI/LLM orchestration architecture of OpsPilot and how they are mitigated.

## 1. Prompt Injection
**Risk**: An attacker submits a malicious payload in the request body designed to override the system prompt, potentially forcing the LLM to output unsafe commands or ignore constraints.
**Mitigation**:
- The system heavily relies on structured output validation using strict Pydantic schemas. If the LLM generates instructions outside the schema, the `validate_structured_output` node will reject it and retry.
- The workflow mandates Human-in-the-Loop (`AWAITING_REVIEW`) before any action is executed.

## 2. Data Leakage
**Risk**: The LLM leaks sensitive information from the Knowledge Base (e.g., secrets accidentally committed to policies) to unauthorized users.
**Mitigation**:
- Implementation of RBAC (Role-Based Access Control) at the retrieval level (future state).
- The vector store is isolated and only queried based on validated backend logic, not directly by user input.
- Strict abstraction of environment variables (LLM APIs) preventing the model from ever seeing runtime credentials.

## 3. Secret Handling
**Risk**: Hardcoded API keys in the repository or logged credentials.
**Mitigation**:
- Secrets are managed entirely through environment variables (`.env`) which is strictly included in `.gitignore`.
- Telemetry and structured logging explicitly strip full payload bodies or mask keys to prevent leakage in observability backends.

## 4. Unsafe Autonomous Actions
**Risk**: The AI performs destructive operational tasks (e.g., shutting down routers) without oversight.
**Mitigation**:
- Strict adherence to ADR-0003 (Mandatory Human Review).
- LangGraph orchestration enforces that the agent possesses no external-world tools. It only yields a `Recommendation` object.

## 5. System DoS via Kafka Queue Exhaustion
**Risk**: Spamming the API with large requests overloads the Kafka broker and ML workers.
**Mitigation**:
- API rate limiting (to be added at API Gateway level).
- Database-enforced Idempotency keys prevent duplicate processing for identical payload fingerprints.
