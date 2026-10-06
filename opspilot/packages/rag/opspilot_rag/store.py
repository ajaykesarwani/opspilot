"""Chroma-backed vector store with a similarity threshold that triggers abstention."""

import logging
from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings

from opspilot_contracts.rag import DEFAULT_MIN_SCORE, ChunkMetadata, ChunkResponse
from opspilot_rag.embedder import Embedder

logger = logging.getLogger(__name__)

COLLECTION_NAME = "opspilot_knowledge_base"


class InsufficientEvidenceError(Exception):
    """No retrieved chunk met the similarity threshold: callers must abstain, not guess."""


class VectorStore:
    def __init__(self, embedder: Embedder, persist_directory: str | None = None) -> None:
        self.embedder = embedder
        if persist_directory:
            self.client = chromadb.PersistentClient(path=persist_directory)
            name = COLLECTION_NAME
        else:
            self.client = chromadb.Client(Settings(is_persistent=False))
            # Ephemeral clients share one in-process backend; a unique name keeps every
            # VectorStore instance isolated (tests, API and worker in the same process).
            name = f"{COLLECTION_NAME}_{uuid4().hex}"
        self.collection = self.client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self.collection.count()

    def add_chunks(self, texts: list[str], metadatas: list[ChunkMetadata]) -> None:
        """Insert or replace chunks. Chunk IDs are deterministic, so re-ingesting a document
        is idempotent."""
        if len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have the same length")
        if not texts:
            return
        self.collection.upsert(
            ids=[f"{m.document_id}:{m.chunk_index}" for m in metadatas],
            embeddings=self.embedder.embed_documents(texts),  # type: ignore[arg-type]
            metadatas=[m.model_dump() for m in metadatas],
            documents=texts,
        )
        logger.info("chunks_upserted", extra={"count": len(texts)})

    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = DEFAULT_MIN_SCORE,
        filters: dict[str, Any] | None = None,
    ) -> list[ChunkResponse]:
        """Return chunks with cosine similarity >= min_score, best first.

        Raises InsufficientEvidenceError when nothing qualifies.
        """
        available = self.collection.count()
        if available == 0:
            raise InsufficientEvidenceError("The knowledge base is empty")

        results = self.collection.query(
            query_embeddings=[self.embedder.embed_query(query)],  # type: ignore[arg-type]
            n_results=min(top_k, available),
            where=filters or None,
            include=["documents", "metadatas", "distances"],
        )
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        chunks = [
            ChunkResponse(
                text=doc,
                metadata=ChunkMetadata.model_validate(meta),
                similarity_score=1.0 - distance,  # cosine distance -> similarity
            )
            for doc, meta, distance in zip(documents, metadatas, distances, strict=True)
            if 1.0 - distance >= min_score
        ]
        if not chunks:
            raise InsufficientEvidenceError("No retrieved chunk met the similarity threshold")
        return chunks
