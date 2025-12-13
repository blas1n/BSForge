"""Content embedding service for RAG.

Wraps BGE-M3 model to generate embeddings for content chunks.
Enriches text with metadata before embedding for better retrieval.
"""

from app.config.rag import EmbeddingConfig
from app.core.logging import get_logger
from app.core.vectordb import VectorDB
from app.models.content_chunk import ChunkPosition

logger = get_logger(__name__)


class ContentEmbedder:
    """Content embedder for RAG system.

    Generates embeddings for content chunks with metadata enrichment.

    Attributes:
        vector_db: VectorDB implementation (provides embed methods)
        config: Embedding configuration
    """

    def __init__(
        self,
        vector_db: VectorDB,
        config: EmbeddingConfig | None = None,
    ):
        """Initialize embedder.

        Args:
            vector_db: VectorDB implementation
            config: Embedding configuration (uses defaults if not provided)
        """
        self.vector_db = vector_db
        self.config = config or EmbeddingConfig()

    async def embed_chunk(
        self,
        text: str,
        position: ChunkPosition | None = None,
        is_opinion: bool = False,
        is_example: bool = False,
        keywords: list[str] | None = None,
    ) -> list[float]:
        """Embed a content chunk with metadata enrichment.

        Prepares text by adding structural tags for better retrieval quality.

        Args:
            text: Chunk text
            position: Structural position (hook/body/conclusion)
            is_opinion: Whether chunk contains opinion
            is_example: Whether chunk contains examples
            keywords: Keywords for the chunk

        Returns:
            Embedding vector
        """
        enriched_text = self._prepare_text(
            text=text,
            position=position,
            is_opinion=is_opinion,
            is_example=is_example,
            keywords=keywords,
        )

        return await self.vector_db.embed(enriched_text)

    async def embed_batch(
        self,
        chunks: list[tuple[str, dict]],
    ) -> list[list[float]]:
        """Embed multiple chunks in batch.

        More efficient than calling embed_chunk() multiple times.

        Args:
            chunks: List of (text, metadata) tuples where metadata contains:
                - position: ChunkPosition
                - is_opinion: bool
                - is_example: bool
                - keywords: list[str]

        Returns:
            List of embedding vectors
        """
        enriched_texts = [
            self._prepare_text(
                text=text,
                position=meta.get("position"),
                is_opinion=meta.get("is_opinion", False),
                is_example=meta.get("is_example", False),
                keywords=meta.get("keywords"),
            )
            for text, meta in chunks
        ]

        return await self.vector_db.embed_batch(enriched_texts)

    def _prepare_text(
        self,
        text: str,
        position: ChunkPosition | None,
        is_opinion: bool,
        is_example: bool,
        keywords: list[str] | None,
    ) -> str:
        """Prepare text for embedding by adding metadata tags.

        Args:
            text: Original text
            position: Structural position
            is_opinion: Opinion flag
            is_example: Example flag
            keywords: Keywords list

        Returns:
            Enriched text with metadata tags
        """
        parts = []

        # Add position tag
        if position == ChunkPosition.HOOK:
            parts.append("[HOOK]")
        elif position == ChunkPosition.CONCLUSION:
            parts.append("[CONCLUSION]")

        # Add characteristic tags
        if is_opinion:
            parts.append("[OPINION]")
        if is_example:
            parts.append("[EXAMPLE]")

        # Add keywords
        if keywords:
            keyword_str = ", ".join(keywords[:5])  # Limit to 5 keywords
            parts.append(f"[KEYWORDS: {keyword_str}]")

        # Add original text
        parts.append(text)

        return " ".join(parts)


__all__ = ["ContentEmbedder"]
