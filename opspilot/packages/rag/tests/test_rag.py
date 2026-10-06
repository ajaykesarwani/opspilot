import json
from pathlib import Path

import pytest

from opspilot_contracts.rag import DEFAULT_MIN_SCORE
from opspilot_rag import (
    DocumentChunker,
    HashingEmbedder,
    InsufficientEvidenceError,
    VectorStore,
    load_knowledge_base,
)

KB = Path(__file__).parents[3] / "data" / "knowledge_base"


@pytest.fixture(scope="module")
def store() -> VectorStore:
    s = VectorStore(HashingEmbedder())
    load_knowledge_base(s, KB)
    return s


def test_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder()
    a, b = e.embed_query("refund approval"), e.embed_query("refund approval")
    assert a == b
    assert sum(x * x for x in a) == pytest.approx(1.0)


def test_embedder_has_real_similarity_signal():
    e = HashingEmbedder()
    q = e.embed_query("who approves refunds")
    related = e.embed_query("Refunds are approved by Tier 1 support")
    unrelated = e.embed_query("The quarterly marketing offsite is in June")
    dot = lambda x, y: sum(i * j for i, j in zip(x, y, strict=True))  # noqa: E731
    assert dot(q, related) > dot(q, unrelated) + 0.2


def test_global_random_state_is_untouched():
    import random

    random.seed(123)
    expected = random.random()
    random.seed(123)
    HashingEmbedder().embed_query("anything")
    assert random.random() == expected


def test_retrieves_the_relevant_policy_section(store):
    [top, *_] = store.search("How long does account deletion take?", top_k=2)
    assert "Account Deletion" in top.text


def test_abstains_on_unrelated_query(store):
    with pytest.raises(InsufficientEvidenceError):
        store.search("What is the capital of France?")


def test_empty_store_abstains():
    with pytest.raises(InsufficientEvidenceError):
        VectorStore(HashingEmbedder()).search("anything")


def test_stores_are_isolated_from_each_other():
    a, b = VectorStore(HashingEmbedder()), VectorStore(HashingEmbedder())
    load_knowledge_base(a, KB)
    assert a.count() > 0 and b.count() == 0


def test_reloading_the_knowledge_base_is_idempotent():
    s = VectorStore(HashingEmbedder())
    first = load_knowledge_base(s, KB)
    load_knowledge_base(s, KB)
    assert s.count() == first


def test_golden_dataset_meets_quality_floor(store):
    """The same measurement the evaluation pipeline reports, enforced as a regression test."""
    cases = json.loads((KB / "golden_dataset.json").read_text())
    answerable = [c for c in cases if c["expected_source"]]
    unanswerable = [c for c in cases if not c["expected_source"]]

    def hits(q):
        try:
            return store.search(q, top_k=2, min_score=DEFAULT_MIN_SCORE)
        except InsufficientEvidenceError:
            return []

    recall = sum(
        any(h.metadata.source == c["expected_source"] for h in hits(c["question"]))
        for c in answerable
    ) / len(answerable)
    abstained = sum(not hits(c["question"]) for c in unanswerable) / len(unanswerable)
    assert recall >= 0.8, recall
    assert abstained >= 0.7, abstained


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, 20), (10, -1)])
def test_chunker_rejects_invalid_sizes(size, overlap):
    with pytest.raises(ValueError):
        DocumentChunker(size, overlap)


def test_chunker_terminates_and_respects_size_on_long_text():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = DocumentChunker(chunk_size=100, chunk_overlap=20).chunk(text)
    assert len(chunks) > 5
    assert all(len(c) <= 100 for c in chunks)
    assert set(" ".join(chunks).split()) == set(text.split())  # nothing lost


def test_chunker_splits_on_headings_and_keeps_heading_with_body():
    chunks = DocumentChunker(chunk_size=500).chunk("# A\nalpha text\n\n## B\nbeta text")
    assert chunks == ["# A\nalpha text", "## B\nbeta text"]


def test_chunker_handles_empty_and_giant_token():
    assert DocumentChunker().chunk("   ") == []
    assert len(DocumentChunker(chunk_size=10, chunk_overlap=2).chunk("x" * 100)) == 1
