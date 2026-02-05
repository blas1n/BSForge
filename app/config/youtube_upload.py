"""YouTube upload and analytics configuration models.

This module provides typed Pydantic configuration for YouTube upload and analytics:
- Schedule preferences (optimal upload times)
- YouTube API settings (upload, thumbnails)
- Analytics collection settings
"""

from typing import Literal

from pydantic import BaseModel, Field


class SchedulePreferenceConfig(BaseModel):
    """Configuration for upload scheduling preferences.

    Attributes:
        allowed_hours: Hours when uploads are allowed (0-23)
        preferred_days: Preferred days of week (0=Mon, 6=Sun), None=all days
        min_interval_hours: Minimum hours between uploads for same channel
        max_daily_uploads: Maximum uploads per day per channel
        timezone: Timezone for scheduling
        use_optimal_time: Whether to use analytics-based optimal time
    """

    allowed_hours: list[int] = Field(
        default_factory=lambda: list(range(9, 22)),
        description="Hours when uploads allowed (0-23)",
    )
    preferred_days: list[int] | None = Field(
        default=None, description="Preferred days (0=Mon, 6=Sun), None=all days"
    )
    min_interval_hours: int = Field(
        default=4, ge=1, le=24, description="Minimum hours between uploads"
    )
    max_daily_uploads: int = Field(default=3, ge=1, le=10, description="Maximum uploads per day")
    timezone: str = Field(default="Asia/Seoul", description="Timezone for scheduling")
    use_optimal_time: bool = Field(default=True, description="Use analytics-based optimal time")


class YouTubeAPIConfig(BaseModel):
    """Configuration for YouTube API operations.

    Attributes:
        default_category_id: Default YouTube category ID (28=Science & Tech)
        default_privacy: Default privacy status for uploads
        chunk_size_mb: Upload chunk size in MB for resumable uploads
        max_retries: Maximum retry attempts for failed uploads
        retry_delay_seconds: Delay between retries in seconds
        thumbnail_upload_enabled: Whether to upload custom thumbnails
        processing_poll_interval: Seconds between processing status checks
        processing_timeout: Max seconds to wait for processing
    """

    default_category_id: str = Field(
        default="28", description="YouTube category ID (28=Science & Tech)"
    )
    default_privacy: Literal["public", "private", "unlisted"] = Field(
        default="private", description="Default privacy status"
    )
    chunk_size_mb: int = Field(default=1, ge=1, le=256, description="Upload chunk size in MB")
    max_retries: int = Field(default=3, ge=1, le=10, description="Max retry attempts")
    retry_delay_seconds: int = Field(default=5, ge=1, le=60, description="Delay between retries")
    thumbnail_upload_enabled: bool = Field(default=True, description="Enable thumbnail upload")
    processing_poll_interval: int = Field(
        default=30, ge=10, le=300, description="Seconds between processing checks"
    )
    processing_timeout: int = Field(
        default=3600, ge=300, le=7200, description="Max wait for processing"
    )


class AnalyticsConfig(BaseModel):
    """Configuration for YouTube Analytics collection.

    Attributes:
        sync_interval_hours: Hours between analytics sync
        metrics_lookback_days: Days of historical data to analyze
        performance_percentile: Percentile threshold for high performers
        min_sample_size: Minimum videos for reliable time analysis
        engagement_weight: Weight for engagement in scoring (vs views)
    """

    sync_interval_hours: int = Field(
        default=6, ge=1, le=24, description="Hours between analytics sync"
    )
    metrics_lookback_days: int = Field(
        default=90, ge=7, le=365, description="Days of historical data"
    )
    performance_percentile: float = Field(
        default=90.0, ge=50.0, le=99.0, description="High performer percentile"
    )
    min_sample_size: int = Field(
        default=10, ge=5, le=100, description="Min videos for time analysis"
    )
    engagement_weight: float = Field(
        default=0.4, ge=0.0, le=1.0, description="Engagement weight in scoring"
    )


class YouTubeUploadPipelineConfig(BaseModel):
    """Complete YouTube upload pipeline configuration.

    All sub-configs have defaults and can be used without explicit configuration.

    Attributes:
        schedule: Schedule preference configuration
        youtube_api: YouTube API configuration
        analytics: Analytics collection configuration
    """

    schedule: SchedulePreferenceConfig = Field(default_factory=SchedulePreferenceConfig)
    youtube_api: YouTubeAPIConfig = Field(default_factory=YouTubeAPIConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)


__all__ = [
    "SchedulePreferenceConfig",
    "YouTubeAPIConfig",
    "AnalyticsConfig",
    "YouTubeUploadPipelineConfig",
]
