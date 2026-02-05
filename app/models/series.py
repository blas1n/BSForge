"""Series ORM model.

This module defines the Series model for tracking content series
that share common themes or topics.
"""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.topic import Topic


class SeriesStatus(str, enum.Enum):
    """Series lifecycle status."""

    ACTIVE = "active"  # Currently tracking
    PAUSED = "paused"  # Temporarily disabled
    ENDED = "ended"  # Series concluded


class Series(Base, UUIDMixin, TimestampMixin):
    """Content series for grouping related topics.

    Tracks series of videos that share common themes, enabling
    series-level analytics and automated detection of related content.

    Attributes:
        channel_id: Foreign key to channels table
        name: Series name
        description: Series description
        criteria_keywords: Keywords for matching topics to series
        criteria_categories: Categories for matching topics
        min_similarity: Minimum similarity for topic clustering
        episode_count: Number of episodes in series
        avg_views: Average views across episodes
        avg_engagement: Average engagement rate
        trend: Performance trend (up, down, stable)
        status: Current series status
        auto_detected: Whether series was auto-detected
        confirmed_by_user: Whether user confirmed the series
        channel: Associated channel
        topics: Associated topics
    """

    __tablename__ = "series"

    # Foreign Key
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Series Info
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Detection Criteria
    criteria_keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    criteria_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    min_similarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)

    # Aggregated Performance
    episode_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_views: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_engagement: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trend: Mapped[str] = mapped_column(String(20), nullable=False, default="stable")

    # Status
    status: Mapped[SeriesStatus] = mapped_column(
        String(20), nullable=False, default=SeriesStatus.ACTIVE
    )

    # Detection Metadata
    auto_detected: Mapped[bool] = mapped_column(nullable=False, default=True)
    confirmed_by_user: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="series_list")
    topics: Mapped[list["Topic"]] = relationship("Topic", back_populates="series")

    # Indexes
    __table_args__ = (
        Index("idx_series_channel", "channel_id"),
        Index("idx_series_status", "status"),
        Index("idx_series_channel_status", "channel_id", "status"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Series(id={self.id}, name={self.name}, "
            f"episodes={self.episode_count}, status={self.status})>"
        )

    @property
    def is_active(self) -> bool:
        """Check if series is active.

        Returns:
            True if series status is ACTIVE
        """
        return self.status == SeriesStatus.ACTIVE


__all__ = [
    "Series",
    "SeriesStatus",
]
