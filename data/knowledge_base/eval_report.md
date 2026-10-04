# OpsPilot Evaluation Report

**Date:** 2026-10-03T22:58:16.686465+00:00

## Metrics
- **recall_at_k_rate**: 1.00
- **abstention_correctness_rate**: 0.40
- **structured_output_validity_rate**: 1.00
- **workflow_completion_rate**: 1.00
- **average_latency_ms**: 29.65

## MLflow Integration
Metrics have been logged to local MLflow tracking. LangGraph autologging/tracing is not fully applied because `mlflow.langchain.autolog()` has limitations with arbitrary state graphs, but tracking boundaries are established.
