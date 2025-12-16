"""PostgreSQL + pgvector implementation of VectorDB protocol.

Unified database for metadata and vector embeddings using pgvector extension.
"""

from datetime import datetime
from typing import Any

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.types import SessionFactory
from app.models.content_chunk import ContentChunk

logger = get_logger(__name__)


class PgVectorDB:
    """PostgreSQL + pgvector implementation for vector storage.

    Implements the VectorDB protocol using PostgreSQL with pgvector extension.
    Embeddings are stored directly in the ContentChunk table.

    Attributes:
        db_session_factory: Async session factory
        embedding_model: SentenceTransformer model
        model_name: Embedding model name
        dimensions: Embedding dimensions
    """

    def __init__(
        self,
        db_session_factory: SessionFactory,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
    ):
        """Initialize PgVectorDB.

        Args:
            db_session_factory: SQLAlchemy async session factory
            model_name: HuggingFace model identifier
            device: Device to use (cpu, cuda, mps)
        """
        self.db_session_factory = db_session_factory
        self.model_name = model_name
        self.device = device

        # Initialize embedding model
        logger.info(f"Loading embedding model: {model_name} on {device}")
        self.embedding_model = SentenceTransformer(model_name, device=device)
        self.dimensions = self.embedding_model.get_sentence_embedding_dimension()

        logger.info(f"PgVectorDB ready (dim={self.dimensions})")

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        # SentenceTransformer.encode() is synchronous
        embedding = self.embedding_model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 10,
        )
        return [emb.tolist() for emb in embeddings]

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
            namespace: Channel ID to filter by (format: "channel_{uuid}")

        Returns:
            List of (chunk_id, similarity_score) tuples
        """
        async with self.db_session_factory() as session:
            # Build query with vector similarity
            query = select(
                ContentChunk.id,
                ContentChunk.embedding.cosine_distance(vector).label("distance"),
            )

            # Filter by namespace (channel_id)
            if namespace:
                # Extract channel_id from namespace (format: "channel_{uuid}")
                channel_id = namespace.replace("channel_", "")
                query = query.where(ContentChunk.channel_id == channel_id)

            # Filter by created_at
            if filter_after:
                query = query.where(ContentChunk.created_at >= filter_after)

            # Filter only chunks with embeddings
            query = query.where(ContentChunk.embedding.is_not(None))

            # Order by similarity and limit
            query = query.order_by("distance").limit(top_k)

            result = await session.execute(query)
            rows = result.all()

            # Convert distance to similarity (1 - distance for cosine)
            return [(str(row.id), 1.0 - row.distance) for row in rows]

    async def upsert(
        self,
        doc_id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> None:
        """Insert or update a vector.

        Note: This method is kept for protocol compatibility but is not used
        in the pgvector implementation. Embeddings are stored directly via
        ContentChunk model updates.

        Args:
            doc_id: ContentChunk UUID
            vector: Embedding vector
            metadata: Optional metadata (not used in pgvector)
            namespace: Channel namespace (not used in pgvector)
        """
        logger.warning(
            "PgVectorDB.upsert() called but not needed - "
            "embeddings are stored via ContentChunk model directly"
        )

    async def upsert_batch(
        self,
        items: list[tuple[str, list[float], dict[str, Any] | None]],
        namespace: str | None = None,
    ) -> None:
        """Insert or update multiple vectors.

        Note: This method is kept for protocol compatibility but is not used
        in the pgvector implementation. Embeddings are stored directly via
        ContentChunk model updates.

        Args:
            items: List of (doc_id, vector, metadata) tuples
            namespace: Channel namespace (not used in pgvector)
        """
        logger.warning(
            "PgVectorDB.upsert_batch() called but not needed - "
            "embeddings are stored via ContentChunk model directly"
        )

    async def delete(
        self,
        doc_ids: list[str],
        namespace: str | None = None,
    ) -> None:
        """Delete vectors by IDs.

        Note: This method is kept for protocol compatibility but is not used
        in the pgvector implementation. Embeddings are deleted via
        ContentChunk model cascade deletes.

        Args:
            doc_ids: List of ContentChunk UUIDs
            namespace: Channel namespace (not used in pgvector)
        """
        logger.warning(
            "PgVectorDB.delete() called but not needed - "
            "embeddings are deleted via ContentChunk cascade delete"
        )


__all__ = ["PgVectorDB"]
