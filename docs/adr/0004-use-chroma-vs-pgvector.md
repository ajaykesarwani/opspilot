# ADR 0004: Use Chroma Now, Prepare for pgvector

## Context
We need a local vector database for Retrieval-Augmented Generation (RAG).

## Decision
For the initial local portfolio version, we selected ChromaDB running in-memory or on local disk, rather than immediately adopting PostgreSQL with pgvector.

## Rationale
- **Simplicity**: Chroma requires no complex setup or Docker extensions for local development and easily integrates with Mock embeddings.
- **Portability**: It allows the `opspilot-rag` package to be tested purely in Python without external container dependencies.

## What would change for pgvector
When moving to production, we would switch to `pgvector`:
1. **Infrastructure**: We would swap the Postgres image in `docker-compose.yml` to `pgvector/pgvector:pg16`.
2. **Implementation**: The `VectorStore` protocol in `opspilot_rag.store` would be implemented by a new `PgVectorStore` class using SQLAlchemy and `pgvector` operators (`<=>` for cosine distance).
3. **Operations**: It would simplify our operational stack by reducing the number of distinct databases to manage, keeping relational workflow state and embeddings in the same persistence layer.
