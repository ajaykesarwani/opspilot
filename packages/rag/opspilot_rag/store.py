from typing import List, Optional, Dict, Any
import logging
import chromadb
from chromadb.config import Settings

from opspilot_contracts.rag import ChunkMetadata, ChunkResponse
from opspilot_rag.embedder import Embedder

logger = logging.getLogger(__name__)

class InsufficientEvidenceError(Exception):
    pass

class VectorStore:
    def __init__(self, embedder: Embedder, persist_directory: Optional[str] = None):
        self.embedder = embedder
        if persist_directory:
            self.client = chromadb.PersistentClient(path=persist_directory)
        else:
            self.client = chromadb.Client(Settings(is_persistent=False))
            
        self.collection = self.client.get_or_create_collection(
            name="opspilot_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, texts: List[str], metadatas: List[ChunkMetadata]) -> None:
        if not texts:
            return
            
        embeddings = self.embedder.embed_documents(texts)
        ids = [f"{m.document_id}_{m.chunk_index}" for m in metadatas]
        
        # Convert Pydantic models to dicts for Chroma
        chroma_metadatas = [m.model_dump() for m in metadatas]
        
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=chroma_metadatas,
            documents=texts
        )
        logger.info(f"Added {len(texts)} chunks to vector store")

    def search(
        self, 
        query: str, 
        top_k: int = 3, 
        min_score: float = 0.6,
        filters: Optional[Dict[str, str]] = None
    ) -> List[ChunkResponse]:
        query_embedding = self.embedder.embed_query(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results["documents"] or not results["documents"][0]:
            raise InsufficientEvidenceError("No chunks found matching the criteria")
            
        chunks = []
        for doc, meta, distance in zip(
            results["documents"][0], 
            results["metadatas"][0], 
            results["distances"][0]
        ):
            # Convert distance to a pseudo similarity score
            # Depending on distance metric, we can map it. We'll assume cosine distance [0, 2]
            # similarity = 1 - distance
            similarity_score = 1.0 - distance
            
            if similarity_score >= min_score:
                chunks.append(
                    ChunkResponse(
                        text=doc,
                        metadata=ChunkMetadata.model_validate(meta),
                        similarity_score=similarity_score
                    )
                )
                
        if not chunks:
            raise InsufficientEvidenceError("Retrieved chunks are below the confidence threshold")
            
        return chunks
