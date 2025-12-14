"""Video ORM model.

This module defines the Video model for generated videos with metadata,
file paths, and lifecycle tracking.
"""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.script import Script


class VideoStatus(str, enum.Enum):
    """Video lifecycle status."""

    GENERATING = "generating"  # Currently being generated
    GENERATED = "generated"  # Generation complete, awaiting review
    REVIEWED = "reviewed"  # Reviewed by human
    APPROVED = "approved"  # Approved for upload
    REJECTED = "rejected"  # Rejected, won't use
    UPLOADED = "uploaded"  # Uploaded to YouTube
    FAILED = "failed"  # Generation failed
    ARCHIVED = "archived"  # Archived


class Video(Base, UUIDMixin, TimestampMixin):
    """Generated video with metadata.

    Stores videos generated from scripts with file paths, generation metadata,
    lifecycle status, and relationships to scripts and channels.

    Attributes:
        channel_id: Foreign key to channels table
        script_id: Foreign key to scripts table
        video_path: Path to video file
        thumbnail_path: Path to thumbnail image
        audio_path: Path to audio file
        subtitle_path: Path to subtitle file
        duration_seconds: Video duration in seconds
        file_size_bytes: Video file size in bytes
        resolution: Video resolution (e.g., "1080x1920")
        fps: Frames per second
        tts_service: TTS service used (e.g., "edge-tts", "elevenlabs")
        tts_voice_id: TTS voice identifier
        visual_sources: List of visual sources used (JSONB)
        generation_time_seconds: Time taken to generate in seconds
        generation_metadata: Additional generation info (JSONB)
        error_message: Error message if generation failed
        status: Current video status
        channel: Associated channel
        script: Associated script
    """

    __tablename__ = "videos"

    # Foreign Keys
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # File Paths
    video_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=False)
    audio_path: Mapped[str | None] = mapped_column(String(500))
    subtitle_path: Mapped[str | None] = mapped_column(String(500))

    # Video Metadata
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False, default="1080x1920")
    fps: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # Generation Info
    tts_service: Mapped[str] = mapped_column(String(50), nullable=False)
    tts_voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    visual_sources: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    generation_time_seconds: Mapped[int | None] = mapped_column(Integer)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Error Handling
    error_message: Mapped[str | None] = mapped_column(Text)

    # Status
    status: Mapped[VideoStatus] = mapped_column(
        String(20),
        nullable=False,
        default=VideoStatus.GENERATING,
        index=True,
    )

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="videos")
    script: Mapped["Script"] = relationship("Script", back_populates="videos")
    # NOTE: upload relationship will be added in Phase 6

    # Composite Indexes
    __table_args__ = (
        Index("idx_video_channel_status", "channel_id", "status"),
        Index("idx_video_script", "script_id"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Video(id={self.id}, script_id={self.script_id}, status={self.status})>"


__all__ = [
    "Video",
    "VideoStatus",
]
