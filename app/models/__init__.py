"""SQLAlchemy ORM models.

Models are organized by feature and created incrementally:
- Phase 3: Channel, Persona, Source, Topic
- Phase 4: Script
- Phase 5: Video
- Phase 6: Upload, Performance, Series
"""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.channel import Channel, ChannelStatus, Persona, TTSService
from app.models.performance import Performance
from app.models.script import Script, ScriptStatus
from app.models.series import Series, SeriesStatus
from app.models.source import Source, SourceRegion, SourceType, channel_sources
from app.models.topic import Topic, TopicStatus
from app.models.upload import PrivacyStatus, Upload, UploadStatus
from app.models.video import Video, VideoStatus

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    # Phase 3 Models
    "Channel",
    "ChannelStatus",
    "Persona",
    "TTSService",
    "Source",
    "SourceType",
    "SourceRegion",
    "channel_sources",
    "Topic",
    "TopicStatus",
    # Phase 4 Models
    "Script",
    "ScriptStatus",
    # Phase 5 Models
    "Video",
    "VideoStatus",
    # Phase 6 Models
    "Upload",
    "UploadStatus",
    "PrivacyStatus",
    "Performance",
    "Series",
    "SeriesStatus",
]
