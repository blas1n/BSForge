"""Content generation configuration models."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.config.validators import validate_range_list


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


class TopicCollectionConfig(BaseModel):
    """Topic collection configuration.

    Attributes:
        sources: Source types to collect from (reddit, google_trends, rss)
        target_language: Target language for translation
        source_overrides: Source-specific overrides
    """

    sources: list[str] = Field(default_factory=list)
    target_language: str = Field(default="ko")
    source_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, v: list[str]) -> list[str]:
        """Validate that at least one source is configured."""
        if not v:
            raise ValueError("At least one source must be configured")
        return v


class DedupConfig(BaseModel):
    """Configuration for topic deduplication.

    Hash-only deduplication via DB check.
    """

    hash_ttl_days: int = Field(
        default=7, ge=1, le=30, description="Days to consider for deduplication"
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
        video_template: Video template name for styling
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
        """Validate max_daily >= daily_target."""
        if info.data.get("daily_target") and v < info.data["daily_target"]:
            raise ValueError("max_daily must be >= daily_target")
        return v
