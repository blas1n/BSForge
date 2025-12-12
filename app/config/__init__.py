"""Channel configuration models."""

from pydantic import BaseModel, Field

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
from app.config.filtering import (
    CategoryFilter,
    ExcludeFilters,
    IncludeFilters,
    KeywordFilter,
    TopicFilterConfig,
)
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
    """

    channel: ChannelInfo
    persona: PersonaConfig
    topic_collection: TopicCollectionConfig
    scoring: ScoringConfig
    content: ContentConfig
    upload: UploadConfig
    operation: OperationConfig = Field(default_factory=OperationConfig)


__all__ = [
    # Channel
    "ChannelInfo",
    "YouTubeConfig",
    # Filtering
    "TopicFilterConfig",
    "IncludeFilters",
    "ExcludeFilters",
    "CategoryFilter",
    "KeywordFilter",
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
    # Main
    "ChannelConfig",
]
