"""Channel configuration models."""

from pydantic import BaseModel, Field

from app.config.bgm import BGMConfig, BGMTrack
from app.config.channel import ChannelInfo, YouTubeConfig
from app.config.content import (
    ContentConfig,
    DedupConfig,
    QueueConfig,
    RegionWeights,
    ScheduleConfig,
    ScoringConfig,
    ScoringWeights,
    SourceOverride,
    SubtitleConfig,
    TopicCollectionConfig,
    TrendConfig,
    UploadConfig,
    VisualConfig,
)
from app.config.filtering import FilteringConfig
from app.config.operation import (
    AutoApproveConfig,
    NotificationConfig,
    OperationConfig,
    ReviewGates,
)
from app.config.persona import (
    AvoidPatterns,
    CommunicationStyle,
    PersonaConfig,
    Perspective,
    SpeechPatterns,
    VoiceConfig,
    VoiceSettings,
)
from app.config.series import SeriesConfig, SeriesCriteria, SeriesMatcherConfig
from app.config.sources import (
    GoogleTrendsConfig,
    HackerNewsConfig,
    RedditConfig,
    RSSConfig,
    WebScraperConfig,
    YouTubeTrendingConfig,
)


class ChannelConfig(BaseModel):
    """Complete channel configuration.

    Attributes:
        channel: Channel information
        persona: Persona configuration
        topic_collection: Topic collection settings
        scoring: Scoring configuration
        content: Content generation settings
        upload: Upload settings
        operation: Operation mode settings
        bgm: Background music configuration
    """

    channel: ChannelInfo
    persona: PersonaConfig
    topic_collection: TopicCollectionConfig
    filtering: FilteringConfig = Field(default_factory=FilteringConfig)
    scoring: ScoringConfig
    content: ContentConfig
    upload: UploadConfig
    operation: OperationConfig = Field(default_factory=OperationConfig)
    bgm: BGMConfig = Field(default_factory=BGMConfig)


__all__ = [
    # BGM
    "BGMConfig",
    "BGMTrack",
    # Channel
    "ChannelInfo",
    "YouTubeConfig",
    # Filtering
    "FilteringConfig",
    # Persona
    "PersonaConfig",
    "VoiceConfig",
    "VoiceSettings",
    "CommunicationStyle",
    "SpeechPatterns",
    "AvoidPatterns",
    "Perspective",
    # Content
    "TopicCollectionConfig",
    "RegionWeights",
    "SourceOverride",
    "TrendConfig",
    "ScoringConfig",
    "ScoringWeights",
    "QueueConfig",
    "DedupConfig",
    "ContentConfig",
    "VisualConfig",
    "SubtitleConfig",
    "UploadConfig",
    "ScheduleConfig",
    # Operation
    "OperationConfig",
    "ReviewGates",
    "AutoApproveConfig",
    "NotificationConfig",
    # Series
    "SeriesCriteria",
    "SeriesConfig",
    "SeriesMatcherConfig",
    # Sources
    "HackerNewsConfig",
    "RedditConfig",
    "RSSConfig",
    "GoogleTrendsConfig",
    "YouTubeTrendingConfig",
    "WebScraperConfig",
    # Main
    "ChannelConfig",
]
