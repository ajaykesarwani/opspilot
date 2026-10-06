import logging
from datetime import UTC, datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

from opspilot_api.deps import VectorStoreDep
from opspilot_contracts.rag import (
    ChunkMetadata,
    DocumentIngestRequest,
    RetrievalRequest,
    RetrievalResponse,
)
from opspilot_rag.chunker import DocumentChunker, generate_content_hash
from opspilot_rag.store import InsufficientEvidenceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["rag"])
chunker = DocumentChunker()


class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    content_hash: str


@router.post("/documents/ingest", status_code=status.HTTP_201_CREATED)
def ingest_document(payload: DocumentIngestRequest, vector_store: VectorStoreDep) -> IngestResponse:
    """Ingest into THIS API process's knowledge base (see README: Known Limitations)."""
    content_hash = generate_content_hash(payload.content)
    chunks = chunker.chunk(payload.content)
    created_at = datetime.now(UTC).isoformat()
    vector_store.add_chunks(
        chunks,
        [
            ChunkMetadata(
                document_id=payload.document_id,
                title=payload.title,
                source=payload.source,
                version=payload.version,
                tags=",".join(payload.tags),
                created_at=created_at,
                content_hash=content_hash,
                chunk_index=i,
            )
            for i in range(len(chunks))
        ],
    )
    return IngestResponse(
        document_id=payload.document_id, chunks_created=len(chunks), content_hash=content_hash
    )


@router.post("/retrieval/search")
def search_documents(payload: RetrievalRequest, vector_store: VectorStoreDep) -> RetrievalResponse:
    try:
        chunks = vector_store.search(
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            filters=payload.filters,
        )
    except InsufficientEvidenceError:
        return RetrievalResponse(chunks=[], insufficient_evidence=True)
    return RetrievalResponse(chunks=chunks, insufficient_evidence=False)
