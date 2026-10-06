def test_ingest_then_search_and_abstain(client):
    ingest = client.post(
        "/api/v1/documents/ingest",
        json={
            "document_id": "refunds",
            "title": "Refunds",
            "source": "refunds.md",
            "content": "# Refunds\nRefunds under 50 dollars are approved by Tier 1 support.",
        },
    )
    assert ingest.status_code == 201

    hit = client.post("/api/v1/retrieval/search", json={"query": "who approves refunds"}).json()
    assert hit["insufficient_evidence"] is False
    assert hit["chunks"][0]["metadata"]["source"] == "refunds.md"

    miss = client.post("/api/v1/retrieval/search", json={"query": "capital of France"}).json()
    assert miss["insufficient_evidence"] is True


def test_reingest_is_idempotent(client):
    body = {
        "document_id": "d",
        "title": "t",
        "source": "s",
        "content": "# H\nsome policy text here",
    }
    client.post("/api/v1/documents/ingest", json=body)
    client.post("/api/v1/documents/ingest", json=body)
    hits = client.post(
        "/api/v1/retrieval/search",
        json={"query": "some policy text here", "top_k": 10, "filters": {"document_id": "d"}},
    ).json()["chunks"]
    assert len(hits) == 1


def test_oversized_and_invalid_input_rejected(client):
    too_big = {"document_id": "d", "title": "t", "source": "s", "content": "x" * 200_001}
    assert client.post("/api/v1/documents/ingest", json=too_big).status_code == 422
    assert (
        client.post("/api/v1/retrieval/search", json={"query": "q", "top_k": 999}).status_code
        == 422
    )
    bad_id = {"document_id": "../etc", "title": "t", "source": "s", "content": "c"}
    assert client.post("/api/v1/documents/ingest", json=bad_id).status_code == 422
