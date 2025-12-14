"""Source ORM model and M:N relationship with Channel.

This module defines sources for topic collection and their channel associations.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.topic import Topic


class SourceType(str, enum.Enum):
    """Source collection method type."""

    API = "api"  # REST API (Reddit, HackerNews)
    RSS = "rss"  # RSS/Atom feeds
    SCRAPER = "scraper"  # HTML scraping (communities)
    BROWSER = "browser"  # Headless browser (dynamic sites)
    VIDEO = "video"  # YouTube, TikTok
    SOCIAL = "social"  # Twitter, Instagram
    TREND = "trend"  # Google Trends, Naver DataLab


class SourceRegion(str, enum.Enum):
    """Source geographic region."""

    DOMESTIC = "domestic"  # Korean sources
    FOREIGN = "foreign"  # International sources
    GLOBAL = "global"  # Global platforms


# M:N Association Table
channel_sources = Table(
    "channel_sources",
    Base.metadata,
    Column("channel_id", ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True),
    Column("source_id", ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True),
    Column("weight", Float, nullable=False, default=1.0),
    Column("custom_config", JSON, default=dict),
    Column("enabled", Boolean, nullable=False, default=True),
)


class Source(Base, UUIDMixin, TimestampMixin):
    """Topic collection source.

    Represents an external source for collecting topics (Reddit, blogs, etc.).
    Sources can be associated with multiple channels via M:N relationship.

    Attributes:
        name: Unique source identifier (e.g., "reddit-programming")
        type: Collection method type
        region: Geographic region
        connection_config: Connection settings (JSONB)
        parser_config: Parsing configuration (JSONB)
        default_filters: Default filtering rules (JSONB)
        cron_expression: Collection schedule (cron format)
        rate_limit: Rate limit (requests per minute)
        credibility: Source credibility score (1-10)
        categories: Source categories
        language: Primary language code
        is_active: Whether source is active
        last_collected_at: Last successful collection timestamp
        channels: Associated channels (M:N)
        topics: Collected topics (1:N)
    """

    __tablename__ = "sources"

    # Basic Info
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False, index=True)
    region: Mapped[SourceRegion] = mapped_column(Enum(SourceRegion), nullable=False)

    # Configuration (JSONB for flexibility)
    connection_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    parser_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    default_filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Scheduling
    cron_expression: Mapped[str | None] = mapped_column(String(50))
    rate_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # Quality Metrics
    credibility: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    categories: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    channels: Mapped[list["Channel"]] = relationship(
        "Channel", secondary=channel_sources, back_populates="sources"
    )
    topics: Mapped[list["Topic"]] = relationship(
        "Topic", back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Source(id={self.id}, name={self.name}, type={self.type})>"


__all__ = [
    "Source",
    "SourceType",
    "SourceRegion",
    "channel_sources",
]
