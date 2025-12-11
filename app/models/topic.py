"""Topic ORM model.

This module defines the Topic model for collected and scored topics.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.source import Source


class TopicStatus(str, enum.Enum):
    """Topic lifecycle status."""

    PENDING = "pending"  # Collected, awaiting review
    APPROVED = "approved"  # Approved for script generation
    REJECTED = "rejected"  # Rejected, won't be used
    USED = "used"  # Script/video generated
    EXPIRED = "expired"  # Past expiration time


class Topic(Base, UUIDMixin, TimestampMixin):
    """Collected and scored topic.

    Represents a topic collected from external sources, normalized, deduplicated,
    and scored for relevance to a channel.

    Attributes:
        channel_id: Foreign key to channels table
        source_id: Foreign key to sources table
        title_original: Original title from source
        title_translated: Translated title (if needed)
        title_normalized: Cleaned and normalized title
        summary: Auto-generated summary
        source_url: Original source URL
        categories: Topic categories
        keywords: Extracted keywords
        entities: Named entities (person, company, product, etc.) as JSONB
        language: Detected language code
        score_source: Source credibility score (0-1)
        score_freshness: Time-based freshness score (0-1)
        score_trend: Trend momentum score (0-1)
        score_relevance: Channel relevance score (0-1)
        score_total: Total weighted score (0-100)
        status: Current topic status
        published_at: When topic was published at source
        expires_at: When topic expires based on category
        content_hash: SHA-256 hash for deduplication
        channel: Associated channel
        source: Associated source
    """

    __tablename__ = "topics"

    # Foreign Keys
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    # NOTE: series_id FK will be added in Phase 6 when Series model is implemented

    # Title Variants
    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    title_translated: Mapped[str | None] = mapped_column(Text)
    title_normalized: Mapped[str] = mapped_column(Text, nullable=False)

    # Content
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Classification
    categories: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    entities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # Scoring (0-1 for components, 0-100 for total)
    score_source: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_freshness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_trend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    # Status
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus),
        nullable=False,
        default=TopicStatus.PENDING,
        index=True,
    )

    # Timestamps
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Deduplication
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="topics")
    source: Mapped["Source"] = relationship("Source", back_populates="topics")

    # Composite Indexes
    __table_args__ = (
        Index("idx_topic_channel_status", "channel_id", "status"),
        Index("idx_topic_score", "channel_id", "score_total"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Topic(id={self.id}, title={self.title_normalized[:50]}, score={self.score_total})>"
        )


__all__ = [
    "Topic",
    "TopicStatus",
]
