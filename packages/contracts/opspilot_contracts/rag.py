from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class DocumentIngestRequest(BaseModel):
    document_id: str
    title: str
    source: str
    version: str = "1.0"
    tags: List[str] = Field(default_factory=list)
    content: str

class ChunkMetadata(BaseModel):
    document_id: str
    title: str
    source: str
    version: str
    tags: str  # Chroma metadata typically requires strings, int, or float. We will join tags with commas.
    created_at: str
    content_hash: str
    chunk_index: int

class ChunkResponse(BaseModel):
    text: str
    metadata: ChunkMetadata
    similarity_score: float

class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 3
    min_score: float = 0.6  # Threshold for abstention
    filters: Optional[Dict[str, str]] = None

class RetrievalResponse(BaseModel):
    chunks: List[ChunkResponse]
    insufficient_evidence: bool = False
