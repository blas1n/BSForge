"""Upload ORM model.

This module defines the Upload model for YouTube video uploads with metadata,
scheduling information, and lifecycle tracking.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.performance import Performance
    from app.models.video import Video


class PrivacyStatus(str, enum.Enum):
    """YouTube video privacy status."""

    PUBLIC = "public"  # Visible to everyone
    PRIVATE = "private"  # Only visible to owner
    UNLISTED = "unlisted"  # Visible to anyone with the link


class UploadStatus(str, enum.Enum):
    """Upload lifecycle status."""

    PENDING = "pending"  # Waiting to be scheduled
    SCHEDULED = "scheduled"  # Scheduled for upload
    UPLOADING = "uploading"  # Currently uploading
    PROCESSING = "processing"  # YouTube processing
    COMPLETED = "completed"  # Successfully uploaded
    FAILED = "failed"  # Upload failed


class Upload(Base, UUIDMixin, TimestampMixin):
    """YouTube video upload with metadata and scheduling.

    Stores upload information for videos including YouTube video ID,
    metadata (title, description, tags), scheduling info, and upload status.

    Attributes:
        video_id: Foreign key to videos table (one-to-one)
        youtube_video_id: YouTube's video ID after upload
        youtube_url: Full URL to YouTube video
        title: Video title (max 100 chars)
        description: Video description (max 5000 chars)
        tags: List of video tags
        category_id: YouTube category ID
        privacy_status: Video privacy setting
        is_shorts: Whether this is a YouTube Short
        scheduled_at: Scheduled upload time
        uploaded_at: Actual upload time
        published_at: Time when video became public
        upload_status: Current upload status
        error_message: Error message if upload failed
        video: Associated video (one-to-one)
        performance: Associated performance metrics (one-to-one)
    """

    __tablename__ = "uploads"

    # Foreign Key (one-to-one with Video)
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # YouTube Info (populated after upload)
    youtube_video_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    youtube_url: Mapped[str | None] = mapped_column(String(200))

    # Metadata
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    category_id: Mapped[str] = mapped_column(String(10), nullable=False, default="28")

    # Visibility Settings
    privacy_status: Mapped[PrivacyStatus] = mapped_column(
        String(20), nullable=False, default=PrivacyStatus.PRIVATE
    )
    is_shorts: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Scheduling
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Status
    upload_status: Mapped[UploadStatus] = mapped_column(
        String(20), nullable=False, default=UploadStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    video: Mapped["Video"] = relationship("Video", back_populates="upload")
    performance: Mapped["Performance"] = relationship(
        "Performance", back_populates="upload", uselist=False
    )

    # Composite Indexes
    __table_args__ = (
        Index("idx_upload_youtube_id", "youtube_video_id"),
        Index("idx_upload_scheduled", "scheduled_at"),
        Index("idx_upload_status", "upload_status"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Upload(id={self.id}, video_id={self.video_id}, "
            f"youtube_id={self.youtube_video_id}, status={self.upload_status})>"
        )


__all__ = [
    "Upload",
    "UploadStatus",
    "PrivacyStatus",
]
