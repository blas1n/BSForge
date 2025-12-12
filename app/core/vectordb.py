"""Vector database interface and utilities.

This module defines the protocol for vector database operations.
Implementations will be provided for:
- Chroma (development)
- Pinecone (production)

Usage:
    from app.core.vectordb import VectorDB

    class MyService:
        def __init__(self, vector_db: VectorDB):
            self.vector_db = vector_db

        async def find_similar(self, text: str) -> list[str]:
            embedding = await self.vector_db.embed(text)
            results = await self.vector_db.query(embedding, top_k=5)
            return [doc_id for doc_id, score in results]
"""

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class VectorDB(Protocol):
    """Protocol for vector database operations.

    This interface supports both topic deduplication (Phase 3)
    and RAG retrieval (Phase 4).

    Implementations:
    - ChromaVectorDB: Local development using Chroma
    - PineconeVectorDB: Production using Pinecone

    All methods are async to support non-blocking I/O.
    """

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (dimension depends on model)
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        More efficient than calling embed() multiple times.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        ...

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_after: datetime | None = None,
        namespace: str | None = None,
    ) -> list[tuple[str, float]]:
        """Query similar vectors.

        Args:
            vector: Query embedding vector
            top_k: Number of results to return
            filter_after: Only return items indexed after this time
            namespace: Optional namespace/collection to search in

        Returns:
            List of (document_id, similarity_score) tuples,
            sorted by similarity descending
        """
        ...

    async def upsert(
        self,
        doc_id: str,
        vector: list[float],
        metadata: dict | None = None,
        namespace: str | None = None,
    ) -> None:
        """Insert or update a vector.

        Args:
            doc_id: Unique document identifier
            vector: Embedding vector
            metadata: Optional metadata to store with vector
            namespace: Optional namespace/collection
        """
        ...

    async def upsert_batch(
        self,
        items: list[tuple[str, list[float], dict | None]],
        namespace: str | None = None,
    ) -> None:
        """Insert or update multiple vectors.

        Args:
            items: List of (doc_id, vector, metadata) tuples
            namespace: Optional namespace/collection
        """
        ...

    async def delete(
        self,
        doc_ids: list[str],
        namespace: str | None = None,
    ) -> None:
        """Delete vectors by IDs.

        Args:
            doc_ids: List of document IDs to delete
            namespace: Optional namespace/collection
        """
        ...


__all__ = ["VectorDB"]
