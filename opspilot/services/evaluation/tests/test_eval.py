import json

from opspilot_evaluation.run_eval import (
    BASELINE_PATH,
    GATED_METRICS,
    KB_DIR,
    build_store,
    compare_to_baseline,
    evaluate,
)


def test_current_metrics_do_not_regress_against_committed_baseline():
    cases = json.loads((KB_DIR / "golden_dataset.json").read_text())
    metrics, rows = evaluate(build_store(), cases)
    assert len(rows) == len(cases)
    assert compare_to_baseline(metrics, json.loads(BASELINE_PATH.read_text())) == []


def test_regressions_are_detected():
    baseline = {m: 0.9 for m in GATED_METRICS}
    worse = {m: 0.5 for m in GATED_METRICS}
    assert len(compare_to_baseline(worse, baseline)) == len(GATED_METRICS)
    assert compare_to_baseline(baseline, baseline) == []


def test_metrics_are_not_trivially_perfect_or_zero():
    metrics, _ = evaluate(build_store(), json.loads((KB_DIR / "golden_dataset.json").read_text()))
    assert 0.5 < metrics["recall_at_k"] <= 1.0
    assert 0.5 < metrics["abstention_recall"] <= 1.0
    assert metrics["structured_output_validity"] == 1.0
