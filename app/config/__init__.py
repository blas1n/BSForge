"""Channel configuration models."""

from pydantic import BaseModel, Field

from app.config.bgm import BGMConfig, BGMTrack
from app.config.channel import ChannelInfo, YouTubeConfig
from app.config.content import (
    ContentConfig,
    ContentVisualConfig,
    DedupConfig,
    ScheduleConfig,
    SourceOverride,
    SubtitleConfig,
    TopicCollectionConfig,
    UploadConfig,
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
    RedditConfig,
    RSSConfig,
)
from app.config.youtube_upload import (
    AnalyticsConfig,
    SchedulePreferenceConfig,
    YouTubeAPIConfig,
    YouTubeUploadPipelineConfig,
)


class ChannelConfig(BaseModel):
    """Complete channel configuration.

    Attributes:
        channel: Channel information
        persona: Persona configuration
        topic_collection: Topic collection settings
        content: Content generation settings
        upload: Upload settings
        operation: Operation mode settings
        bgm: Background music configuration
    """

    channel: ChannelInfo
    persona: PersonaConfig
    topic_collection: TopicCollectionConfig
    filtering: FilteringConfig = Field(default_factory=FilteringConfig)
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
    "SourceOverride",
    "DedupConfig",
    "ContentConfig",
    "ContentVisualConfig",
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
    "RedditConfig",
    "RSSConfig",
    "GoogleTrendsConfig",
    # Main
    "ChannelConfig",
    # YouTube Upload & Analytics
    "SchedulePreferenceConfig",
    "YouTubeAPIConfig",
    "AnalyticsConfig",
    "YouTubeUploadPipelineConfig",
]
