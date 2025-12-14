"""Channel and Persona ORM models.

This module defines the core models for managing YouTube channels and their AI personas.
"""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.content_chunk import ContentChunk
    from app.models.script import Script
    from app.models.source import Source
    from app.models.topic import Topic
    from app.models.video import Video


class ChannelStatus(str, enum.Enum):
    """Channel operational status."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Channel(Base, UUIDMixin, TimestampMixin):
    """YouTube channel configuration and metadata.

    Stores channel information and configuration as JSONB for flexibility.
    Each channel has one persona and many topics.

    Attributes:
        name: Channel display name
        description: Channel description
        youtube_channel_id: YouTube channel ID (unique)
        youtube_handle: YouTube handle (@username)
        status: Current operational status
        topic_config: Topic collection settings (JSONB)
        source_config: Source configuration (JSONB)
        content_config: Content generation settings (JSONB)
        operation_config: Operation mode settings (JSONB)
        default_hashtags: Default hashtags for videos
        default_links: Default links for video descriptions
        persona: Associated persona (1:1)
        topics: Associated topics (1:N)
    """

    __tablename__ = "channels"

    # Basic Info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # YouTube Integration
    youtube_channel_id: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    youtube_handle: Mapped[str | None] = mapped_column(String(50))

    # Status
    status: Mapped[ChannelStatus] = mapped_column(
        Enum(ChannelStatus),
        nullable=False,
        default=ChannelStatus.ACTIVE,
        index=True,
    )

    # Configuration (JSONB for flexibility)
    topic_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    content_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    operation_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Defaults
    default_hashtags: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    default_links: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    # Relationships
    persona: Mapped["Persona"] = relationship(
        "Persona", back_populates="channel", uselist=False, cascade="all, delete-orphan"
    )
    topics: Mapped[list["Topic"]] = relationship(
        "Topic", back_populates="channel", cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(
        "Source", secondary="channel_sources", back_populates="channels"
    )
    scripts: Mapped[list["Script"]] = relationship(
        "Script", back_populates="channel", cascade="all, delete-orphan"
    )
    content_chunks: Mapped[list["ContentChunk"]] = relationship(
        "ContentChunk", back_populates="channel", cascade="all, delete-orphan"
    )
    videos: Mapped[list["Video"]] = relationship(
        "Video", back_populates="channel", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Channel(id={self.id}, name={self.name}, status={self.status})>"


class TTSService(str, enum.Enum):
    """Text-to-Speech service provider."""

    EDGE_TTS = "edge-tts"
    ELEVENLABS = "elevenlabs"
    CLOVA = "clova"


class Persona(Base, UUIDMixin, TimestampMixin):
    """AI persona configuration for a channel.

    Each channel has one persona that defines voice, communication style,
    and personality for content generation.

    Attributes:
        channel_id: Foreign key to channels table (unique)
        name: Persona name
        tagline: Short tagline describing the persona
        description: Detailed persona description
        expertise: Areas of expertise
        voice_gender: Voice gender (male, female, neutral)
        tts_service: TTS service provider
        voice_id: Voice ID from TTS service
        voice_settings: Voice configuration (JSONB)
        communication_style: Communication patterns (JSONB)
        perspective: Viewpoint and values (JSONB)
        examples: Example phrases/responses (JSONB)
        channel: Associated channel (1:1)
    """

    __tablename__ = "personas"

    # Foreign Key
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Basic Info
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    expertise: Mapped[list[str] | None] = mapped_column(ARRAY(String))

    # Voice Configuration
    voice_gender: Mapped[str | None] = mapped_column(String(10))
    tts_service: Mapped[TTSService] = mapped_column(
        Enum(TTSService), nullable=False, default=TTSService.EDGE_TTS
    )
    voice_id: Mapped[str | None] = mapped_column(String(100))
    voice_settings: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Personality (JSONB for flexibility)
    communication_style: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    perspective: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    examples: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="persona")

    def __repr__(self) -> str:
        """String representation."""
        return f"<Persona(id={self.id}, name={self.name}, channel_id={self.channel_id})>"


__all__ = [
    "Channel",
    "ChannelStatus",
    "Persona",
    "TTSService",
]
