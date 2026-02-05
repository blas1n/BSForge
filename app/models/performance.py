"""Performance ORM model.

This module defines the Performance model for YouTube video analytics
and performance metrics tracking.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.upload import Upload


class Performance(Base, UUIDMixin, TimestampMixin):
    """YouTube video performance metrics.

    Stores analytics data fetched from YouTube Analytics API including
    view counts, engagement metrics, watch time, and demographic breakdowns.

    Attributes:
        upload_id: Foreign key to uploads table (one-to-one)
        views: Total view count
        likes: Total likes
        dislikes: Total dislikes
        comments: Total comments
        shares: Total shares
        watch_time_seconds: Total watch time in seconds
        avg_view_duration: Average view duration in seconds
        avg_view_percentage: Average percentage of video watched
        engagement_rate: Calculated engagement rate
        ctr: Click-through rate
        subscribers_gained: Subscribers gained from this video
        subscribers_lost: Subscribers lost from this video
        traffic_sources: Traffic source breakdown (JSONB)
        demographics: Viewer demographics (JSONB)
        daily_snapshots: Historical daily metrics (JSONB)
        last_synced_at: Last time metrics were synced
        is_high_performer: Whether video is a high performer
        added_to_training: Whether added to training dataset
        upload: Associated upload (one-to-one)
    """

    __tablename__ = "performances"

    # Foreign Key (one-to-one with Upload)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Basic Metrics
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dislikes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Watch Metrics
    watch_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_view_duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_view_percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Computed Metrics
    engagement_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Subscriber Impact
    subscribers_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subscribers_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Detailed Breakdowns (JSONB)
    traffic_sources: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    demographics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    daily_snapshots: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    # Sync & Analysis
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_high_performer: Mapped[bool] = mapped_column(nullable=False, default=False)
    added_to_training: Mapped[bool] = mapped_column(nullable=False, default=False)

    # Relationships
    upload: Mapped["Upload"] = relationship("Upload", back_populates="performance")

    # Indexes
    __table_args__ = (
        Index("idx_performance_high", "is_high_performer"),
        Index("idx_performance_views", "views"),
        Index("idx_performance_upload", "upload_id"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Performance(id={self.id}, upload_id={self.upload_id}, "
            f"views={self.views}, engagement_rate={self.engagement_rate:.2f})>"
        )

    @property
    def net_subscribers(self) -> int:
        """Calculate net subscriber impact.

        Returns:
            Net subscribers gained minus lost
        """
        return self.subscribers_gained - self.subscribers_lost

    def calculate_engagement_rate(self) -> float:
        """Calculate engagement rate from likes and comments.

        Returns:
            Engagement rate as (likes + comments) / views
        """
        if self.views == 0:
            return 0.0
        return (self.likes + self.comments) / self.views


__all__ = [
    "Performance",
]
