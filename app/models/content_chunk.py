"""ContentChunk ORM model.

This module defines the ContentChunk model for storing chunked content
with vector embeddings for RAG retrieval.
"""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.script import Script


class ChunkPosition(str, enum.Enum):
    """Position of chunk in script."""

    HOOK = "hook"
    BODY = "body"
    CONCLUSION = "conclusion"


class ContentType(str, enum.Enum):
    """Type of content stored."""

    SCRIPT = "script"  # Published script
    DRAFT = "draft"  # Draft script
    OUTLINE = "outline"  # Outline/notes
    NOTE = "note"  # Opinion/perspective note


class ContentChunk(Base, UUIDMixin, TimestampMixin):
    """Chunked content for RAG retrieval.

    Stores content chunks with metadata and vector embeddings for semantic search.
    Vector embeddings are stored directly in PostgreSQL using pgvector extension.

    Attributes:
        channel_id: Foreign key to channels
        script_id: Foreign key to scripts (nullable for non-script content)
        content_type: Type of content
        text: Chunk text content
        chunk_index: Position in original content (0-based)
        position: Structural position (hook/body/conclusion)
        context_before: Previous chunk summary for context
        context_after: Next chunk summary for context
        is_opinion: Whether chunk contains opinion/perspective
        is_example: Whether chunk contains examples
        is_analogy: Whether chunk uses analogies
        terms: Terms extracted from chunk
        embedding: Vector embedding (1024 dimensions for BGE-M3)
        embedding_model: Model used for embedding
        performance_score: Performance score if from published content (0-1)
        channel: Associated channel
        script: Associated script (if applicable)
    """

    __tablename__ = "content_chunks"

    # Foreign Keys
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), index=True
    )

    # Content Type
    content_type: Mapped[ContentType] = mapped_column(
        String(20), nullable=False, default=ContentType.SCRIPT, index=True
    )

    # Chunk Content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[ChunkPosition] = mapped_column(String(20), nullable=False, index=True)

    # Context
    context_before: Mapped[str | None] = mapped_column(Text)
    context_after: Mapped[str | None] = mapped_column(Text)

    # Characteristics (for filtering)
    is_opinion: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    is_example: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    is_analogy: Mapped[bool] = mapped_column(nullable=False, default=False)
    terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Vector Embedding (stored in PostgreSQL via pgvector)
    embedding: Mapped[Any] = mapped_column(Vector(1024), nullable=True)  # BGE-M3 dimension
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    # Performance (if published)
    performance_score: Mapped[float | None] = mapped_column(Float, index=True)

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="content_chunks")
    script: Mapped["Script | None"] = relationship("Script", back_populates="content_chunks")

    # Composite Indexes
    __table_args__ = (
        Index("idx_chunk_channel_type", "channel_id", "content_type"),
        Index("idx_chunk_characteristics", "is_opinion", "is_example"),
        Index("idx_chunk_performance", "channel_id", "performance_score"),
        # Vector similarity index (HNSW for fast ANN search)
        Index(
            "idx_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<ContentChunk(id={self.id}, type={self.content_type}, position={self.position})>"


__all__ = [
    "ContentChunk",
    "ChunkPosition",
    "ContentType",
]
