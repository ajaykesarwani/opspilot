"""Load a directory of markdown documents into a VectorStore (idempotent)."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from opspilot_contracts.rag import ChunkMetadata
from opspilot_rag.chunker import DocumentChunker, generate_content_hash
from opspilot_rag.store import VectorStore

logger = logging.getLogger(__name__)

# Files in the knowledge-base directory that are evaluation fixtures, not knowledge.
_EXCLUDED = {"eval_report.md"}


def load_knowledge_base(
    store: VectorStore, directory: str | Path, chunker: DocumentChunker | None = None
) -> int:
    """Chunk and upsert every `*.md` file in `directory`. Returns the number of chunks."""
    chunker = chunker or DocumentChunker()
    root = Path(directory)
    if not root.is_dir():
        logger.warning("knowledge_base_missing", extra={"directory": str(root)})
        return 0

    total = 0
    for path in sorted(root.glob("*.md")):
        if path.name in _EXCLUDED:
            continue
        content = path.read_text(encoding="utf-8")
        chunks = chunker.chunk(content)
        content_hash = generate_content_hash(content)
        created_at = datetime.now(UTC).isoformat()
        store.add_chunks(
            chunks,
            [
                ChunkMetadata(
                    document_id=path.stem,
                    title=path.stem.replace("_", " ").title(),
                    source=path.name,
                    version="1.0",
                    tags="knowledge_base",
                    created_at=created_at,
                    content_hash=content_hash,
                    chunk_index=i,
                )
                for i in range(len(chunks))
            ],
        )
        total += len(chunks)
    logger.info("knowledge_base_loaded", extra={"directory": str(root), "chunks": total})
    return total
