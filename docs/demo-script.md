# OpsPilot: 3-Minute Demo Video Script

**Title**: OpsPilot: Observable AI Workflow Platform

**[0:00 - 0:30] Introduction & Architecture**
- **Visual**: Show the Architecture Diagram from the README.
- **Narration**: "Hi, I'm [Your Name], and this is OpsPilot. OpsPilot is an event-driven, evaluation-driven AI orchestration platform. Rather than using unpredictable autonomous agents, it uses strict LangGraph workflows, Kafka for reliable messaging, and mandatory human-in-the-loop approvals for operational safety."

**[0:30 - 1:15] Scenario 1: A Successful Workflow**
- **Visual**: Screen recording of the React UI. Click "Fill Demo Data" and hit "Submit".
- **Narration**: "Here in the local UI, I'm submitting an operational request. The API accepts it, guarantees idempotency in Postgres, and fires a Kafka event. The background worker picks it up, retrieves context via Chroma RAG, and uses an LLM to generate a strict, validated JSON recommendation. Now, it's paused in an `AWAITING_REVIEW` state."
- **Visual**: Operator clicks "Approve & Complete" on the UI.
- **Narration**: "An operator reviews the citations and approves the action, moving it to completion safely."

**[1:15 - 1:45] Scenario 2: Abstention & Safety**
- **Visual**: Submit a vague or unanswerable request.
- **Narration**: "If a user asks something undocumented, OpsPilot doesn't hallucinate. Our RAG pipeline thresholding detects 'Insufficient Evidence', forcing the workflow to explicitly abstain from action. This keeps infrastructure safe."

**[1:45 - 2:30] Scenario 3: Observability (Jaeger & Prometheus)**
- **Visual**: Open Jaeger UI. Show the trace waterfall for a request.
- **Narration**: "Everything is instrumented with OpenTelemetry. Here in Jaeger, we can see the exact lifecycle: the API request, Kafka publishing, consumption, and every individual LangGraph node like `retrieve_context` and `draft_recommendation`. If the LLM failed, we'd see the exception and retry loops right here."
- **Visual**: Show Prometheus metrics endpoint or a Grafana dashboard.
- **Narration**: "We also export Prometheus metrics for workflow durations, success rates, and provider failures, enabling standard DevOps alerting."

**[2:30 - 3:00] Evaluation & Outro**
- **Visual**: Terminal showing `run_eval.py` output and MLflow UI.
- **Narration**: "Finally, I use Evaluation-Driven Development. I have a golden dataset of operational queries. This script evaluates RAG recall, output validity, and abstention correctness, logging everything to local MLflow to prevent regression. OpsPilot bridges the gap between prototype AI and reliable, observable software engineering."
