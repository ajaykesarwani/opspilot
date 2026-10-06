"""Offline evaluation of retrieval and workflow behaviour against the golden dataset.

It measures exactly what runs in production (same chunker, embedder and DEFAULT_MIN_SCORE),
logs to a local MLflow store, writes a per-case report, and (with --check) exits non-zero if a
quality metric regresses against the committed baseline, so CI can gate on it.

    uv run python services/evaluation/opspilot_evaluation/run_eval.py --check
    uv run python services/evaluation/opspilot_evaluation/run_eval.py --update-baseline

Limits: with the mock LLM, answer *text* is not graded; this measures retrieval, abstention and
workflow/schema behaviour. Grading real model output needs a real provider (see README).
"""

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opspilot_contracts.rag import DEFAULT_MIN_SCORE
from opspilot_contracts.requests import OperationalRequestCreate
from opspilot_orchestration import MockLLMProvider, WorkflowState, create_workflow
from opspilot_rag import DocumentChunker, MockEmbedder, VectorStore, load_knowledge_base

ROOT = Path(__file__).resolve().parents[3]
KB_DIR = ROOT / "data" / "knowledge_base"
BASELINE_PATH = KB_DIR / "baseline_metrics.json"
REPORT_DIR = ROOT / "reports"
TOLERANCE = 0.02
# Higher is better for these; latency is informational only.
GATED_METRICS = (
    "recall_at_k",
    "abstention_recall",
    "abstention_accuracy",
    "structured_output_validity",
    "workflow_completion_rate",
)


def build_store() -> VectorStore:
    store = VectorStore(MockEmbedder())
    load_knowledge_base(store, KB_DIR, DocumentChunker())
    return store


def evaluate(
    store: VectorStore, cases: list[dict[str, Any]]
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    workflow = create_workflow(store, MockLLMProvider())
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []

    for i, case in enumerate(cases):
        answerable = case["expected_source"] is not None
        started = time.perf_counter()
        final = workflow.invoke(
            WorkflowState(
                request_id=f"eval-{i}",
                correlation_id=f"eval-corr-{i}",
                request=OperationalRequestCreate(
                    subject="Question",
                    body=case["question"],
                    requester="eval",
                    priority="low",
                ),
            )
        )
        latencies.append((time.perf_counter() - started) * 1000)
        # Recall is measured end to end: what the workflow itself retrieved (subject + body).
        sources = final["citations"]
        rec = final.get("recommendation")
        abstained = bool(final["insufficient_evidence"])
        rows.append(
            {
                "question": case["question"],
                "type": case["type"],
                "answerable": answerable,
                "retrieved_sources": sources,
                "retrieval_hit": answerable and case["expected_source"] in sources,
                "abstained": abstained,
                "abstention_correct": abstained == (not answerable),
                "schema_valid": rec is not None,
                "completed": final["final_status"] == "AWAITING_REVIEW",
            }
        )

    answerable_rows = [r for r in rows if r["answerable"]]
    unanswerable_rows = [r for r in rows if not r["answerable"]]

    def rate(items: list[dict[str, Any]], key: str) -> float:
        return sum(bool(r[key]) for r in items) / len(items) if items else 1.0

    metrics = {
        "recall_at_k": rate(answerable_rows, "retrieval_hit"),
        "abstention_recall": rate(unanswerable_rows, "abstained"),
        "false_abstention_rate": rate(answerable_rows, "abstained"),  # lower is better
        "abstention_accuracy": rate(rows, "abstention_correct"),
        "structured_output_validity": rate(rows, "schema_valid"),
        "workflow_completion_rate": rate(rows, "completed"),
        "p50_latency_ms": statistics.median(latencies),
        "max_latency_ms": max(latencies),
    }
    return {k: round(v, 4) for k, v in metrics.items()}, rows


def compare_to_baseline(metrics: dict[str, float], baseline: dict[str, float]) -> list[str]:
    return [
        f"{name}: {metrics[name]:.3f} < baseline {baseline[name]:.3f} - {TOLERANCE}"
        for name in GATED_METRICS
        if name in baseline and metrics[name] < baseline[name] - TOLERANCE
    ]


def write_report(metrics: dict[str, float], rows: list[dict[str, Any]]) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    path = REPORT_DIR / "eval_report.md"
    lines = [
        "# OpsPilot Evaluation Report",
        "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} "
        f"(mock LLM, hashing embedder, min_score={DEFAULT_MIN_SCORE})",
        "",
        "| Metric | Value |",
        "|---|---|",
        *[f"| {k} | {v:.3f} |" for k, v in metrics.items()],
        "",
        "## Per-case results",
        "",
        "| Type | Question | Retrieved | Abstained | OK |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        ok = (
            r["retrieval_hit"]
            if r["answerable"] and not r["abstained"]
            else r["abstention_correct"]
        )
        lines.append(
            f"| {r['type']} | {r['question']} | {', '.join(r['retrieved_sources']) or '-'} | "
            f"{'yes' if r['abstained'] else 'no'} | {'✅' if ok else '❌'} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def log_to_mlflow(metrics: dict[str, float], report: Path, n_cases: int) -> None:
    import mlflow

    mlflow.set_tracking_uri(f"sqlite:///{ROOT / 'mlruns.db'}")
    mlflow.set_experiment("opspilot_rag_eval")
    with mlflow.start_run():
        mlflow.set_tag("commit", _git_commit())
        mlflow.log_params({"min_score": DEFAULT_MIN_SCORE, "dataset_size": n_cases, "mock": True})
        mlflow.log_metrics(metrics)
        mlflow.log_artifact(str(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail on regression vs baseline")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args(argv)

    cases = json.loads((KB_DIR / "golden_dataset.json").read_text(encoding="utf-8"))
    metrics, rows = evaluate(build_store(), cases)
    report = write_report(metrics, rows)
    if not args.no_mlflow:
        log_to_mlflow(metrics, report, len(cases))

    print(json.dumps(metrics, indent=2))
    print(f"Report: {report}")

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline updated: {BASELINE_PATH}")
        return 0
    if args.check:
        regressions = compare_to_baseline(metrics, json.loads(BASELINE_PATH.read_text()))
        if regressions:
            print("REGRESSION:\n  " + "\n  ".join(regressions), file=sys.stderr)
            return 1
        print("No regression against baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
