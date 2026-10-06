"""Request/response contracts for document ingestion and retrieval."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Shared by the API, the workflow and the evaluation harness so that what is measured offline
# is exactly what runs in production.
DEFAULT_MIN_SCORE = 0.18
MAX_DOCUMENT_CHARS = 200_000


class DocumentIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1.0", max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=20)
    content: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)


class ChunkMetadata(BaseModel):
    document_id: str
    title: str
    source: str
    version: str
    # Chroma metadata values must be scalars, so tags are stored comma-joined.
    tags: str
    created_at: str
    content_hash: str
    chunk_index: int


class ChunkResponse(BaseModel):
    text: str
    metadata: ChunkMetadata
    similarity_score: float


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=3, ge=1, le=20)
    # Chunks scoring below this are discarded; if none remain the system abstains.
    min_score: float = Field(default=DEFAULT_MIN_SCORE, ge=0.0, le=1.0)
    filters: dict[str, Any] | None = None


class RetrievalResponse(BaseModel):
    chunks: list[ChunkResponse]
    insufficient_evidence: bool = False
