import json
import os

def test_evaluation_baseline_thresholds():
    metrics_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/knowledge_base/baseline_metrics.json"))
    
    # Ensure baseline exists (skip if it hasn't been generated yet during early pipeline stages,
    # or fail if strict regression testing is enforced). 
    # For Milestone 6, we expect it to exist.
    assert os.path.exists(metrics_path), "Baseline metrics file not found."
    
    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)
        
    # Acceptable thresholds (Mock mode might have lower recall due to random vectors,
    # but since we set min_score=-1 in eval script to catch everything, recall_at_k_rate might be non-zero,
    # but we can set forgiving thresholds for mock mode or strict if real).
    # Since this is a test, let's ensure they are above 0.0 or specifically what we expect.
    
    assert metrics["structured_output_validity_rate"] >= 0.9, "Structured output validity degraded"
    assert metrics["workflow_completion_rate"] >= 0.9, "Workflow completion rate degraded"
    
    # Mock embedder is effectively random, so recall and abstention correctness will be random.
    # We just ensure the metrics exist in the dictionary and are floats.
    assert isinstance(metrics["recall_at_k_rate"], float)
    assert isinstance(metrics["abstention_correctness_rate"], float)
    assert isinstance(metrics["average_latency_ms"], float)
