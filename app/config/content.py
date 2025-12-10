"""Content generation configuration models."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RegionWeights(BaseModel):
    """Region weight configuration.

    Attributes:
        domestic: Domestic content weight (0-1)
        foreign: Foreign content weight (0-1)
    """

    domestic: float = Field(..., ge=0, le=1, description="Domestic weight")
    foreign: float = Field(..., ge=0, le=1, description="Foreign weight")

    @field_validator("foreign")
    @classmethod
    def validate_weights_sum(cls, v: float, info: Any) -> float:
        """Validate that domestic + foreign = 1.0.

        Args:
            v: Foreign weight value
            info: Validation info containing other fields

        Returns:
            The validated foreign weight

        Raises:
            ValueError: If weights don't sum to 1.0
        """
        if info.data.get("domestic") is not None:
            domestic = info.data["domestic"]
            total = domestic + v
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Weights must sum to 1.0 (got {total})")
        return v


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
    """Topic scoring weights.

    Attributes:
        source_credibility: Source credibility weight
        source_score: Source-specific score weight
        freshness: Freshness weight
        trend: Trend weight
        channel_relevance: Channel relevance weight
        novelty: Novelty weight
        bonus_multi_source: Multi-source bonus weight
    """

    source_credibility: float = Field(..., ge=0, le=1)
    source_score: float = Field(..., ge=0, le=1)
    freshness: float = Field(..., ge=0, le=1)
    trend: float = Field(..., ge=0, le=1)
    channel_relevance: float = Field(..., ge=0, le=1)
    novelty: float = Field(..., ge=0, le=1)
    bonus_multi_source: float = Field(..., ge=0, le=1)

    @field_validator("bonus_multi_source")
    @classmethod
    def validate_weights_sum_to_one(cls, v: float, info: Any) -> float:
        """Validate that all weights sum to 1.0.

        Args:
            v: Bonus multi-source weight
            info: Validation info

        Returns:
            The validated weight

        Raises:
            ValueError: If weights don't sum to 1.0
        """
        if info.data:
            total = sum(
                [
                    info.data.get("source_credibility", 0),
                    info.data.get("source_score", 0),
                    info.data.get("freshness", 0),
                    info.data.get("trend", 0),
                    info.data.get("channel_relevance", 0),
                    info.data.get("novelty", 0),
                    v,
                ]
            )
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Scoring weights must sum to 1.0 (got {total})")
        return v


class ScoringConfig(BaseModel):
    """Scoring configuration.

    Attributes:
        weights: Scoring weights
        preset: Scoring preset name
    """

    weights: ScoringWeights
    preset: Literal["news", "educational", "trending", "niche", "tech"] = Field(
        default="tech", description="Scoring preset"
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
    """

    format: Literal["shorts", "long"] = Field(default="shorts")
    target_duration: int = Field(..., ge=10, le=600, description="Duration in seconds")
    visual: VisualConfig
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)


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
        """Validate hour values.

        Args:
            v: List of hours

        Returns:
            Validated hours

        Raises:
            ValueError: If any hour is out of range
        """
        if any(h < 0 or h > 23 for h in v):
            raise ValueError("Hours must be between 0 and 23")
        return sorted(set(v))

    @field_validator("preferred_days")
    @classmethod
    def validate_days(cls, v: list[int] | None) -> list[int] | None:
        """Validate day values.

        Args:
            v: List of days or None

        Returns:
            Validated days

        Raises:
            ValueError: If any day is out of range
        """
        if v is not None and any(d < 0 or d > 6 for d in v):
            raise ValueError("Days must be between 0 (Monday) and 6 (Sunday)")
        return sorted(set(v)) if v else None


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
