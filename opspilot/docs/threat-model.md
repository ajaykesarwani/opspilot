# OpsPilot Threat Model

Scope: the local reference deployment. Items marked **Not implemented** are real gaps.

## 1. Prompt injection
**Risk**: request text or retrieved documents contain instructions that try to override the system prompt.
**Mitigations (implemented)**
- Request and retrieved context are fenced in `<request>` / `<context>` blocks and the prompt states they are untrusted data (`test_untrusted_text_is_fenced_in_prompt`).
- The model returns a strict Pydantic `Recommendation`; invalid output is retried a bounded number of times, then the workflow fails.
- Citations are filled in from retrieval, not model output, so injected text cannot invent sources.
- If evidence is insufficient the output must be an abstention, otherwise it is rejected.
- The graph has no tools and cannot perform actions; a human must approve (ADR 0003).
**Residual risk**: delimiting reduces but does not eliminate injection against a real model. Needs adversarial evaluation once a real provider exists.

## 2. Data leakage
**Risk**: knowledge-base content reaches users who should not see it.
**Mitigations**: retrieval is only reachable through validated backend logic and `/retrieval/search`.
**Not implemented**: authentication and per-document access control. Anyone who can reach the API can query the knowledge base.

## 3. Secrets
- Configuration is via environment variables; `.env*` is git-ignored except `.env.example`.
- Compose uses throwaway local credentials; Postgres is bound to `127.0.0.1`.
- Request bodies are not written to logs (only IDs, status, priority). Kafka events carry only IDs and priority, never request text.

## 4. Unsafe autonomous action
- The workflow produces a `Recommendation` only. `COMPLETED` is reachable solely via the approve endpoint.
- **Not implemented**: authentication on that endpoint, so the approving identity is not verified.

## 5. Abuse and denial of service
- Input is bounded: field lengths, 200k-character documents, `top_k <= 20`.
- Idempotency keys prevent duplicate work from client retries.
- CORS is restricted to configured origins and credentials are disabled.
- **Not implemented**: rate limiting and request-size limits at the HTTP layer (belongs at a gateway).

## 6. Poison messages
- Malformed events are dead-lettered with reason, source partition/offset and a truncated copy of the payload, instead of blocking the partition or being dropped.
