"""Base interfaces and DTOs for topic collection.

This module defines the core data structures and abstract interfaces
used throughout the topic collection pipeline.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class RawTopic(BaseModel):
    """Raw topic data from external source.

    This is the initial DTO collected from sources (Reddit, HN, RSS, etc.)
    before normalization and processing.

    Attributes:
        source_id: Source identifier (UUID or name)
        source_url: Original URL of the topic
        title: Original title (any language)
        content: Optional content/body text
        published_at: When the topic was published
        metrics: Source-specific metrics (upvotes, views, etc.)
        metadata: Additional source-specific data
    """

    source_id: str
    source_url: HttpUrl
    title: str
    content: str | None = None
    published_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class NormalizedTopic(BaseModel):
    """Normalized topic after processing.

    This DTO represents a topic that has been translated, cleaned,
    classified, and prepared for scoring and storage.

    Attributes:
        source_id: Source UUID
        source_url: Original URL
        title_original: Original title from source
        title_translated: Translated title (if needed)
        title_normalized: Cleaned and normalized title
        summary: Auto-generated summary
        categories: Topic categories (tech, news, science, etc.)
        keywords: Extracted keywords
        entities: Named entities (companies, products, people, etc.)
        language: Detected language code (en, ko, etc.)
        published_at: Publication timestamp
        content_hash: SHA-256 hash for deduplication
        metrics: Original source metrics
    """

    source_id: uuid.UUID
    source_url: HttpUrl
    title_original: str
    title_translated: str | None = None
    title_normalized: str
    summary: str
    categories: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    entities: dict[str, list[str]] = Field(default_factory=dict)
    language: str = "en"
    published_at: datetime | None = None
    content_hash: str
    metrics: dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat(), uuid.UUID: str}


class ScoredTopic(NormalizedTopic):
    """Topic with calculated scores.

    Extends NormalizedTopic with scoring information.
    This DTO represents a fully processed topic with all scoring
    components calculated and ready for storage.

    Attributes:
        score_source: Source engagement score (0-1)
        score_freshness: Time-based freshness score (0-1)
        score_trend: Trend momentum score (0-1)
        score_relevance: Channel relevance score (0-1)
        score_total: Total weighted score (0-100)
    """

    score_source: float = Field(ge=0.0, le=1.0)
    score_freshness: float = Field(ge=0.0, le=1.0)
    score_trend: float = Field(ge=0.0, le=1.0)
    score_relevance: float = Field(ge=0.0, le=1.0)
    score_total: int = Field(ge=0, le=100)


class BaseSource(ABC):
    """Abstract base class for all source collectors.

    Each source type (Reddit, HN, RSS, etc.) implements this interface
    to provide a consistent collection API.

    Attributes:
        config: Source configuration from database
        source_id: UUID of the source
    """

    def __init__(self, config: dict[str, Any], source_id: uuid.UUID):
        """Initialize source collector.

        Args:
            config: Source configuration (connection_config, parser_config, etc.)
            source_id: UUID of the source in database
        """
        self.config = config
        self.source_id = source_id

    @abstractmethod
    async def collect(self, params: dict[str, Any]) -> list[RawTopic]:
        """Collect raw topics from the source.

        Args:
            params: Collection parameters (channel-specific overrides)

        Returns:
            List of raw topics collected from source

        Raises:
            SourceError: If collection fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if source is accessible and healthy.

        Returns:
            True if source is healthy, False otherwise
        """
        pass

    async def validate_config(self) -> bool:
        """Validate source configuration.

        Returns:
            True if config is valid

        Raises:
            ValueError: If configuration is invalid
        """
        # Default implementation - override if needed
        return True


class CollectionResult(BaseModel):
    """Result of a collection operation.

    Contains statistics and collected topics from a source.

    Attributes:
        source_id: Source UUID
        source_name: Source name
        collected_count: Number of raw topics collected
        normalized_count: Number successfully normalized
        deduplicated_count: Number after deduplication
        scored_count: Number successfully scored
        added_to_queue: Number added to priority queue
        errors: List of error messages
        duration_seconds: Time taken for collection
    """

    source_id: uuid.UUID
    source_name: str
    collected_count: int = 0
    normalized_count: int = 0
    deduplicated_count: int = 0
    scored_count: int = 0
    added_to_queue: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

    class Config:
        """Pydantic config."""

        json_encoders = {uuid.UUID: str}


__all__ = [
    "RawTopic",
    "NormalizedTopic",
    "ScoredTopic",
    "BaseSource",
    "CollectionResult",
]
