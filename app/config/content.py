"""Content generation configuration models."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config.validators import validate_range_list, validate_weights_sum


class RegionWeights(BaseModel):
    """Region weight configuration.

    Attributes:
        domestic: Domestic content weight (0-1)
        foreign: Foreign content weight (0-1)
    """

    domestic: float = Field(..., ge=0, le=1, description="Domestic weight")
    foreign: float = Field(..., ge=0, le=1, description="Foreign weight")

    @model_validator(mode="after")
    def check_weights_sum(self) -> "RegionWeights":
        """Validate that domestic + foreign = 1.0."""
        validate_weights_sum(
            {"domestic": self.domestic, "foreign": self.foreign},
        )
        return self


class SourceOverride(BaseModel):
    """Source-specific override configuration.

    Attributes:
        weight: Source weight multiplier
        params: Source-specific parameters
        filters: Source-specific filters
    """

    weight: float = Field(default=1.0, ge=0, le=5.0, description="Source weight")
    params: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)


class TrendConfig(BaseModel):
    """Trend detection configuration.

    Attributes:
        enabled: Whether trend detection is enabled
        sources: Trend sources
        regions: Region codes for trends
        min_growth_rate: Minimum growth rate percentage
    """

    enabled: bool = Field(default=True, description="Enable trend detection")
    sources: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    min_growth_rate: int = Field(default=50, ge=0, description="Minimum growth rate %")


class TopicCollectionConfig(BaseModel):
    """Topic collection configuration.

    Attributes:
        region_weights: Regional content weights
        enabled_sources: List of enabled sources
        source_overrides: Source-specific overrides
        trend_config: Trend detection settings
    """

    region_weights: RegionWeights
    enabled_sources: list[str] = Field(..., min_length=1)
    source_overrides: dict[str, SourceOverride] = Field(default_factory=dict)
    trend_config: TrendConfig = Field(default_factory=TrendConfig)


class ScoringWeights(BaseModel):
    """Weights for each score component.

    All weights must sum to 1.0. Defaults are provided.
    """

    source_credibility: float = Field(default=0.15, ge=0, le=1)
    source_score: float = Field(default=0.15, ge=0, le=1)
    freshness: float = Field(default=0.20, ge=0, le=1)
    trend_momentum: float = Field(default=0.10, ge=0, le=1)
    term_relevance: float = Field(default=0.20, ge=0, le=1)
    entity_relevance: float = Field(default=0.10, ge=0, le=1)
    novelty: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def check_weights_sum(self) -> "ScoringWeights":
        """Validate that all weights sum to 1.0."""
        validate_weights_sum(
            {
                "source_credibility": self.source_credibility,
                "source_score": self.source_score,
                "freshness": self.freshness,
                "trend_momentum": self.trend_momentum,
                "term_relevance": self.term_relevance,
                "entity_relevance": self.entity_relevance,
                "novelty": self.novelty,
            }
        )
        return self


class ScoringConfig(BaseModel):
    """Configuration for topic scoring.

    All fields have defaults - can be used without any configuration.
    """

    weights: ScoringWeights = Field(default_factory=ScoringWeights)

    # Freshness decay settings
    freshness_half_life_hours: int = Field(
        default=24, ge=1, description="Hours for freshness to decay to 0.5"
    )
    freshness_min: float = Field(default=0.1, ge=0, le=1, description="Minimum freshness score")

    # Channel relevance settings (populated from channel config)
    target_terms: list[str] = Field(default_factory=list)
    target_entities: list[str] = Field(default_factory=list)

    # Novelty settings
    novelty_lookback_days: int = Field(
        default=30, ge=1, description="Days to look back for novelty check"
    )

    # Minimum score threshold
    min_score_threshold: int = Field(
        default=30, ge=0, le=100, description="Minimum total score to accept topic"
    )


class QueueConfig(BaseModel):
    """Configuration for topic queue.

    All fields have defaults - can be used without any configuration.
    """

    max_pending_size: int = Field(
        default=100, ge=1, description="Maximum number of pending topics per channel"
    )
    min_score_threshold: int = Field(
        default=30, ge=0, le=100, description="Minimum total score to accept into queue"
    )
    auto_expire_hours: int = Field(
        default=72, ge=1, description="Auto-expire topics after this many hours"
    )


class DedupConfig(BaseModel):
    """Configuration for topic deduplication.

    Hash-only deduplication - only exact content matches are filtered.
    Different articles about the same event are intentionally allowed
    to provide diverse perspectives for richer content generation.

    All fields have defaults - can be used without any configuration.
    """

    # Redis TTL for hash cache
    hash_ttl_days: int = Field(
        default=7, ge=1, le=30, description="Days to keep hashes in Redis cache"
    )


class VisualConfig(BaseModel):
    """Visual content configuration.

    Attributes:
        source_priority: Priority order for visual sources
        fallback_color: Fallback background color (hex)
    """

    source_priority: list[str] = Field(..., min_length=1)
    fallback_color: str = Field(..., pattern=r"^#[0-9a-fA-F]{6}$")


class SubtitleConfig(BaseModel):
    """Subtitle styling configuration.

    Attributes:
        font_name: Font family name
        font_size: Font size in pixels
        position: Subtitle position
        highlight_current_word: Whether to highlight current word
    """

    font_name: str = Field(default="Pretendard")
    font_size: int = Field(default=48, ge=12, le=120)
    position: Literal["top", "middle", "bottom"] = Field(default="bottom")
    highlight_current_word: bool = Field(default=True)


class ContentConfig(BaseModel):
    """Content generation configuration.

    Attributes:
        format: Video format
        target_duration: Target duration in seconds
        visual: Visual settings
        subtitle: Subtitle settings
        video_template: Video template name for styling (e.g., "korean_shorts_standard", "minimal")
    """

    format: Literal["shorts", "long"] = Field(default="shorts")
    target_duration: int = Field(..., ge=10, le=600, description="Duration in seconds")
    visual: VisualConfig
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    video_template: str = Field(
        default="minimal",
        description="Video template name (e.g., 'korean_shorts_standard', 'minimal')",
    )


class ScheduleConfig(BaseModel):
    """Upload schedule configuration.

    Attributes:
        allowed_hours: Hours of day when uploads are allowed (0-23)
        preferred_days: Preferred days of week (0=Monday, null=all days)
        min_interval_hours: Minimum hours between uploads
    """

    allowed_hours: list[int] = Field(..., min_length=1)
    preferred_days: list[int] | None = Field(default=None)
    min_interval_hours: int = Field(..., ge=1, le=168)

    @field_validator("allowed_hours")
    @classmethod
    def validate_hours(cls, v: list[int]) -> list[int]:
        """Validate hour values (0-23), dedupe and sort."""
        return validate_range_list(v, min_val=0, max_val=23, field_name="Hours")

    @field_validator("preferred_days")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        """Validate day values (0-6 for Monday-Sunday), dedupe and sort."""
        if v is None:
            return None
        return validate_range_list(v, min_val=0, max_val=6, field_name="Days")


class UploadConfig(BaseModel):
    """Upload configuration.

    Attributes:
        daily_target: Target uploads per day
        max_daily: Maximum uploads per day
        schedule: Upload schedule settings
        default_hashtags: Default hashtags for uploads
        default_category: YouTube category ID
    """

    daily_target: int = Field(..., ge=1, le=10)
    max_daily: int = Field(..., ge=1, le=20)
    schedule: ScheduleConfig
    default_hashtags: list[str] = Field(default_factory=list)
    default_category: str = Field(default="28")

    @field_validator("max_daily")
    @classmethod
    def validate_max_ge_target(cls, v: int, info: Any) -> int:
        """Validate max_daily >= daily_target.

        Args:
            v: Max daily value
            info: Validation info

        Returns:
            Validated max_daily

        Raises:
            ValueError: If max_daily < daily_target
        """
        if info.data.get("daily_target") and v < info.data["daily_target"]:
            raise ValueError("max_daily must be >= daily_target")
        return v
