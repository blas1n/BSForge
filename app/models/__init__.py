"""SQLAlchemy ORM models.

Models are organized by feature and created incrementally:
- Phase 3: Channel, Persona, Source, Topic
- Phase 4: ContentChunk, Script
- Phase 5: Video
- Phase 6: Upload, Performance, Series
- Phase 7: Experiment
- Phase 8: ReviewQueue
- Phase 10: JobLog
"""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.channel import Channel, ChannelStatus, Persona, TTSService
from app.models.content_chunk import ChunkPosition, ContentChunk, ContentType
from app.models.script import Script, ScriptStatus
from app.models.source import Source, SourceRegion, SourceType, channel_sources
from app.models.topic import Topic, TopicStatus
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
    "ContentChunk",
    "ChunkPosition",
    "ContentType",
    # Phase 5 Models
    "Video",
    "VideoStatus",
]
