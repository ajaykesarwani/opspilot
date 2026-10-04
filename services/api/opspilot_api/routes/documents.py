import logging
from datetime import datetime, UTC
from fastapi import APIRouter, status, HTTPException
from pydantic import BaseModel

from opspilot_api.deps import VectorStoreDep
from opspilot_contracts.rag import DocumentIngestRequest, ChunkMetadata, RetrievalRequest, RetrievalResponse
from opspilot_rag.chunker import DocumentChunker, generate_content_hash
from opspilot_rag.store import InsufficientEvidenceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["rag"])

chunker = DocumentChunker()

class IngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    content_hash: str

@router.post("/documents/ingest", status_code=status.HTTP_201_CREATED, response_model=IngestResponse)
def ingest_document(
    payload: DocumentIngestRequest,
    vector_store: VectorStoreDep
) -> IngestResponse:
    content_hash = generate_content_hash(payload.content)
    
    # Chunk document
    chunks = chunker.chunk(payload.content)
    
    # Prepare metadata
    created_at = datetime.now(UTC).isoformat()
    tags_str = ",".join(payload.tags)
    
    metadatas = [
        ChunkMetadata(
            document_id=payload.document_id,
            title=payload.title,
            source=payload.source,
            version=payload.version,
            tags=tags_str,
            created_at=created_at,
            content_hash=content_hash,
            chunk_index=i
        )
        for i in range(len(chunks))
    ]
    
    # Add to vector store
    vector_store.add_chunks(chunks, metadatas)
    
    return IngestResponse(
        document_id=payload.document_id,
        chunks_created=len(chunks),
        content_hash=content_hash
    )

@router.post("/retrieval/search", response_model=RetrievalResponse)
def search_documents(
    payload: RetrievalRequest,
    vector_store: VectorStoreDep
) -> RetrievalResponse:
    try:
        chunks = vector_store.search(
            query=payload.query,
            top_k=payload.top_k,
            min_score=payload.min_score,
            filters=payload.filters
        )
        return RetrievalResponse(chunks=chunks, insufficient_evidence=False)
    except InsufficientEvidenceError:
        return RetrievalResponse(chunks=[], insufficient_evidence=True)
