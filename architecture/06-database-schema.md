# 🗄️ 데이터베이스 스키마 설계

## 1. 개요

### 1.1 데이터베이스 구조
```
PostgreSQL (메인 DB)
├── 채널/페르소나 관리
├── 주제/스크립트/영상
├── 업로드/성과 추적
└── 검수/시리즈

Redis (캐시/큐)
├── 작업 큐 (Celery)
├── 실시간 상태
└── 중복 체크 캐시

Chroma/Pinecone (벡터 DB)
└── 콘텐츠 임베딩
```

### 1.2 ERD 개요
```
Channel ─┬─ Persona
         ├─ Source (M:N)
         ├─ Topic ──── Script ──── Video ──── Upload
         │                │
         │                └─ Performance
         └─ Series
```

---

## 2. SQLAlchemy 모델

### 2.1 기본 설정
```python
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, JSON, ForeignKey, Table, Enum as SQLEnum,
    UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
import uuid
from enum import Enum


class Base(DeclarativeBase):
    pass


# 공통 Mixin
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
```

### 2.2 채널 (Channel)
```python
class ChannelStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class Channel(Base, UUIDMixin, TimestampMixin):
    """YouTube 채널"""
    __tablename__ = "channels"

    # 기본 정보
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # YouTube 연동
    youtube_channel_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=True)
    youtube_handle: Mapped[str] = mapped_column(String(50), nullable=True)

    # 상태
    status: Mapped[ChannelStatus] = mapped_column(
        SQLEnum(ChannelStatus), default=ChannelStatus.ACTIVE
    )

    # 설정 (JSONB)
    topic_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    operation_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 기본 해시태그/링크
    default_hashtags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    default_links: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # 관계
    persona: Mapped["Persona"] = relationship(back_populates="channel", uselist=False)
    topics: Mapped[list["Topic"]] = relationship(back_populates="channel")
    scripts: Mapped[list["Script"]] = relationship(back_populates="channel")
    videos: Mapped[list["Video"]] = relationship(back_populates="channel")
    series_list: Mapped[list["Series"]] = relationship(back_populates="channel")

    # 인덱스
    __table_args__ = (
        Index("idx_channel_status", "status"),
        Index("idx_channel_youtube_id", "youtube_channel_id"),
    )
```

### 2.3 페르소나 (Persona)
```python
class TTSService(str, Enum):
    EDGE_TTS = "edge-tts"
    ELEVENLABS = "elevenlabs"
    CLOVA = "clova"


class Persona(Base, UUIDMixin, TimestampMixin):
    """채널 페르소나"""
    __tablename__ = "personas"

    # 채널 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), unique=True
    )

    # 정체성
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tagline: Mapped[str] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    expertise: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # 음성 설정
    voice_gender: Mapped[str] = mapped_column(String(10), default="male")
    tts_service: Mapped[TTSService] = mapped_column(
        SQLEnum(TTSService), default=TTSService.EDGE_TTS
    )
    voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    voice_settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 커뮤니케이션 스타일 (JSONB)
    communication_style: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 관점/가치관 (JSONB)
    perspective: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 예시 (JSONB)
    examples: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 관계
    channel: Mapped["Channel"] = relationship(back_populates="persona")
```

### 2.4 소스 (Source)
```python
class SourceType(str, Enum):
    RSS = "rss"
    API = "api"
    SCRAPER = "scraper"
    TREND = "trend"


class SourceRegion(str, Enum):
    DOMESTIC = "domestic"
    FOREIGN = "foreign"
    GLOBAL = "global"


# 채널-소스 다대다 연결 테이블
channel_sources = Table(
    "channel_sources",
    Base.metadata,
    Column("channel_id", UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True),
    Column("source_id", UUID(as_uuid=True), ForeignKey("sources.id"), primary_key=True),
    Column("weight", Float, default=1.0),
    Column("custom_config", JSONB, default=dict),
    Column("enabled", Boolean, default=True),
)


class Source(Base, UUIDMixin, TimestampMixin):
    """주제 수집 소스"""
    __tablename__ = "sources"

    # 기본 정보
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False)
    region: Mapped[SourceRegion] = mapped_column(SQLEnum(SourceRegion), nullable=False)

    # 연결 정보
    connection_config: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # 파싱 설정
    parser_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 필터 설정
    default_filters: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 스케줄
    cron_expression: Mapped[str] = mapped_column(String(50), default="0 */2 * * *")
    rate_limit: Mapped[int] = mapped_column(Integer, default=10)

    # 메타
    credibility: Mapped[float] = mapped_column(Float, default=5.0)  # 1-10
    categories: Mapped[list] = mapped_column(ARRAY(String), default=list)
    language: Mapped[str] = mapped_column(String(10), default="ko")

    # 상태
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_collected_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 관계
    channels: Mapped[list["Channel"]] = relationship(
        secondary=channel_sources,
        backref="sources"
    )
```

### 2.5 주제 (Topic)
```python
class TopicStatus(str, Enum):
    PENDING = "pending"      # Collected, awaiting review
    APPROVED = "approved"    # Approved for script generation
    REJECTED = "rejected"    # Rejected, won't be used
    USED = "used"            # Script/video generated
    EXPIRED = "expired"      # Past expiration time


class Topic(Base, UUIDMixin, TimestampMixin):
    """수집된 주제"""
    __tablename__ = "topics"

    # 채널 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 소스 연결
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    # NOTE: series_id FK will be added in Phase 6 when Series model is implemented

    # 제목
    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    title_translated: Mapped[str | None] = mapped_column(Text)
    title_normalized: Mapped[str] = mapped_column(Text, nullable=False)

    # 내용
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # 분류
    terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    entities: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # 점수 (0-1 for components, 0-100 for total)
    score_source: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_freshness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_trend: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    # 상태
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus), nullable=False, default=TopicStatus.PENDING, index=True
    )

    # 시간
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # 중복 체크용 해시
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 관계
    channel: Mapped["Channel"] = relationship("Channel", back_populates="topics")
    source: Mapped["Source"] = relationship("Source", back_populates="topics")
    scripts: Mapped[list["Script"]] = relationship(
        "Script", back_populates="topic", cascade="all, delete-orphan"
    )

    # 인덱스
    __table_args__ = (
        Index("idx_topic_channel_status", "channel_id", "status"),
        Index("idx_topic_score", "channel_id", "score_total"),
    )
```

### 2.6 스크립트 (Script)
```python
class ScriptStatus(str, Enum):
    GENERATED = "generated"   # Generated, awaiting review
    REVIEWED = "reviewed"     # Reviewed by human
    APPROVED = "approved"     # Approved for production
    REJECTED = "rejected"     # Rejected, won't use
    PRODUCED = "produced"     # Video generated from this


class Script(Base, UUIDMixin, TimestampMixin):
    """생성된 스크립트 (Scene 기반)"""
    __tablename__ = "scripts"

    # 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 스크립트 내용
    script_text: Mapped[str] = mapped_column(Text, nullable=False)  # 전체 텍스트
    title_text: Mapped[str | None] = mapped_column(String(200))  # 영상 오버레이 제목
    scenes: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True, comment="Scene-based script structure"
    )

    # 예상 길이
    estimated_duration: Mapped[int] = mapped_column(Integer, nullable=False)  # 초
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # 품질 체크
    style_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hook_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    forbidden_words: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    quality_passed: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)

    # 생성 메타
    generation_model: Mapped[str] = mapped_column(String(100), nullable=False)
    context_chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # 상태
    status: Mapped[ScriptStatus] = mapped_column(
        String(20), nullable=False, default=ScriptStatus.GENERATED, index=True
    )

    # 관계
    channel: Mapped["Channel"] = relationship("Channel", back_populates="scripts")
    topic: Mapped["Topic"] = relationship("Topic", back_populates="scripts")
    content_chunks: Mapped[list["ContentChunk"]] = relationship(
        "ContentChunk", back_populates="script", cascade="all, delete-orphan"
    )
    videos: Mapped[list["Video"]] = relationship(
        "Video", back_populates="script", cascade="all, delete-orphan"
    )

    # 인덱스
    __table_args__ = (
        Index("idx_script_channel_status", "channel_id", "status"),
        Index("idx_script_quality", "channel_id", "quality_passed"),
    )
```

#### Scene 구조 (JSONB)
```python
# scenes 필드 예시:
[
    {
        "scene_type": "hook",
        "text": "여러분, 이 사실을 알고 계셨나요?",
        "visual_style": "neutral",
        "keyword": "놀라움",
        "visual_hint": "surprised expression",
        "transition_in": "none",
        "duration_hint": 3.0
    },
    {
        "scene_type": "content",
        "text": "최근 연구에 따르면...",
        "visual_style": "neutral",
        "keyword": "연구",
        "visual_hint": "science laboratory"
    },
    {
        "scene_type": "commentary",
        "text": "제 생각에는 이게 정말 중요한 포인트인데요.",
        "visual_style": "persona",
        "keyword": "의견",
        "transition_in": "flash"  # 사실→의견 전환 시 플래시
    }
]
```

### 2.7 영상 (Video)
```python
class VideoStatus(str, Enum):
    GENERATING = "generating"   # Currently being generated
    GENERATED = "generated"     # Generation complete, awaiting review
    REVIEWED = "reviewed"       # Reviewed by human
    APPROVED = "approved"       # Approved for upload
    REJECTED = "rejected"       # Rejected, won't use
    UPLOADED = "uploaded"       # Uploaded to YouTube
    FAILED = "failed"           # Generation failed
    ARCHIVED = "archived"       # Archived


class Video(Base, UUIDMixin, TimestampMixin):
    """생성된 영상"""
    __tablename__ = "videos"

    # 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 파일 경로
    video_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=False)
    audio_path: Mapped[str | None] = mapped_column(String(500))
    subtitle_path: Mapped[str | None] = mapped_column(String(500))

    # 영상 메타
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False, default="1080x1920")
    fps: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    # 생성 정보
    tts_service: Mapped[str] = mapped_column(String(50), nullable=False)
    tts_voice_id: Mapped[str] = mapped_column(String(100), nullable=False)
    visual_sources: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    generation_time_seconds: Mapped[int | None] = mapped_column(Integer)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # 에러 처리
    error_message: Mapped[str | None] = mapped_column(Text)

    # 상태
    status: Mapped[VideoStatus] = mapped_column(
        String(20), nullable=False, default=VideoStatus.GENERATING, index=True
    )

    # 관계
    channel: Mapped["Channel"] = relationship("Channel", back_populates="videos")
    script: Mapped["Script"] = relationship("Script", back_populates="videos")
    # NOTE: upload relationship will be added in Phase 6

    # 인덱스
    __table_args__ = (
        Index("idx_video_channel_status", "channel_id", "status"),
        Index("idx_video_script", "script_id"),
    )
```

---

> **⚠️ Phase 6+ 모델 (미구현)**
>
> 아래 모델들 (2.8~2.13)은 Phase 6 이후에 구현 예정입니다.
> 현재 구현된 모델: Channel, Persona, Source, Topic, Script, ContentChunk, Video

---

### 2.8 업로드 (Upload) - Phase 6 예정
```python
class PrivacyStatus(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"


class Upload(Base, UUIDMixin, TimestampMixin):
    """YouTube 업로드"""
    __tablename__ = "uploads"

    # 영상 연결
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id"), unique=True
    )

    # YouTube 정보
    youtube_video_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=True)
    youtube_url: Mapped[str] = mapped_column(String(200), nullable=True)

    # 메타데이터
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    category_id: Mapped[str] = mapped_column(String(10), default="28")

    # 공개 설정
    privacy_status: Mapped[PrivacyStatus] = mapped_column(
        SQLEnum(PrivacyStatus), default=PrivacyStatus.PRIVATE
    )
    is_shorts: Mapped[bool] = mapped_column(Boolean, default=True)

    # 스케줄
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 상태
    upload_status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # 관계
    video: Mapped["Video"] = relationship(back_populates="upload")
    performance: Mapped["Performance"] = relationship(back_populates="upload", uselist=False)

    # 인덱스
    __table_args__ = (
        Index("idx_upload_youtube_id", "youtube_video_id"),
        Index("idx_upload_scheduled", "scheduled_at"),
    )
```

### 2.9 성과 (Performance) - Phase 6 예정
```python
class Performance(Base, UUIDMixin, TimestampMixin):
    """영상 성과 추적"""
    __tablename__ = "performances"

    # 업로드 연결
    upload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uploads.id"), unique=True
    )

    # 기본 지표
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    dislikes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)

    # 시청 지표
    watch_time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    avg_view_duration: Mapped[float] = mapped_column(Float, default=0)
    avg_view_percentage: Mapped[float] = mapped_column(Float, default=0)

    # 계산 지표
    engagement_rate: Mapped[float] = mapped_column(Float, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0)  # 클릭률

    # 구독자 영향
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0)
    subscribers_lost: Mapped[int] = mapped_column(Integer, default=0)

    # 트래픽 소스 (JSONB)
    traffic_sources: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 인구통계 (JSONB)
    demographics: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 히스토리 (일별 스냅샷)
    daily_snapshots: Mapped[list] = mapped_column(JSONB, default=list)

    # 마지막 동기화
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 파인튜닝 적합성
    is_high_performer: Mapped[bool] = mapped_column(Boolean, default=False)
    added_to_training: Mapped[bool] = mapped_column(Boolean, default=False)

    # 관계
    upload: Mapped["Upload"] = relationship(back_populates="performance")

    # 인덱스
    __table_args__ = (
        Index("idx_performance_high", "is_high_performer"),
        Index("idx_performance_views", "views"),
    )
```

### 2.10 시리즈 (Series) - Phase 6 예정
```python
class SeriesStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class Series(Base, UUIDMixin, TimestampMixin):
    """자동 감지된 시리즈"""
    __tablename__ = "series"

    # 채널 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )

    # 시리즈 정보
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # 시리즈 조건
    criteria_keywords: Mapped[list] = mapped_column(ARRAY(String), default=list)
    criteria_categories: Mapped[list] = mapped_column(ARRAY(String), default=list)
    min_similarity: Mapped[float] = mapped_column(Float, default=0.6)

    # 성과 집계
    episode_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_views: Mapped[float] = mapped_column(Float, default=0)
    avg_engagement: Mapped[float] = mapped_column(Float, default=0)
    trend: Mapped[str] = mapped_column(String(20), default="stable")

    # 상태
    status: Mapped[SeriesStatus] = mapped_column(
        SQLEnum(SeriesStatus), default=SeriesStatus.ACTIVE
    )

    # 자동 감지 여부
    auto_detected: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)

    # 관계
    channel: Mapped["Channel"] = relationship(back_populates="series_list")
    topics: Mapped[list["Topic"]] = relationship(back_populates="series")
```

### 2.11 검수 큐 (ReviewQueue) - Phase 8 예정
```python
class ReviewType(str, Enum):
    TOPIC = "topic"
    SCRIPT = "script"
    VIDEO = "video"
    UPLOAD = "upload"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ReviewQueue(Base, UUIDMixin, TimestampMixin):
    """검수 큐"""
    __tablename__ = "review_queue"

    # 대상 정보
    review_type: Mapped[ReviewType] = mapped_column(SQLEnum(ReviewType), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )

    # 상태
    status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus), default=ReviewStatus.PENDING
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 높을수록 우선

    # 리스크 정보
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    risk_reasons: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # AI 분석 결과 (JSONB)
    ai_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 검수 결과
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(100), nullable=True)
    review_action: Mapped[str] = mapped_column(String(20), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, nullable=True)

    # 만료
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 알림
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # 인덱스
    __table_args__ = (
        Index("idx_review_status_priority", "status", "priority"),
        Index("idx_review_channel_type", "channel_id", "review_type"),
        Index("idx_review_expires", "expires_at"),
        UniqueConstraint("review_type", "target_id", name="uq_review_target"),
    )
```

### 2.12 콘텐츠 청크 (pgvector 임베딩 포함)
```python
class ChunkPosition(str, Enum):
    HOOK = "hook"
    BODY = "body"
    CONCLUSION = "conclusion"


class ContentType(str, Enum):
    SCRIPT = "script"
    DRAFT = "draft"
    OUTLINE = "outline"
    NOTE = "note"


class ContentChunk(Base, UUIDMixin, TimestampMixin):
    """콘텐츠 청크 (pgvector 임베딩 포함)"""
    __tablename__ = "content_chunks"

    # 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), index=True
    )

    # 콘텐츠 타입
    content_type: Mapped[ContentType] = mapped_column(
        String(20), nullable=False, default=ContentType.SCRIPT, index=True
    )

    # 청크 정보
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[ChunkPosition] = mapped_column(String(20), nullable=False, index=True)

    # 컨텍스트
    context_before: Mapped[str | None] = mapped_column(Text)
    context_after: Mapped[str | None] = mapped_column(Text)

    # 특성 (필터링용)
    is_opinion: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    is_example: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    is_analogy: Mapped[bool] = mapped_column(nullable=False, default=False)
    terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # 벡터 임베딩 (pgvector)
    embedding: Mapped[Any] = mapped_column(Vector(1024), nullable=True)  # BGE-M3
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    # 성과 점수 (published 콘텐츠용)
    performance_score: Mapped[float | None] = mapped_column(Float, index=True)

    # 관계
    channel: Mapped["Channel"] = relationship("Channel", back_populates="content_chunks")
    script: Mapped["Script | None"] = relationship("Script", back_populates="content_chunks")

    # 인덱스
    __table_args__ = (
        Index("idx_chunk_channel_type", "channel_id", "content_type"),
        Index("idx_chunk_characteristics", "is_opinion", "is_example"),
        Index("idx_chunk_performance", "channel_id", "performance_score"),
        # HNSW 벡터 인덱스
        Index(
            "idx_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
```

### 2.13 작업 로그 (JobLog) - Phase 10 예정
```python
class JobType(str, Enum):
    COLLECT = "collect"
    GENERATE_SCRIPT = "generate_script"
    GENERATE_VIDEO = "generate_video"
    UPLOAD = "upload"
    SYNC_ANALYTICS = "sync_analytics"
    DETECT_SERIES = "detect_series"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobLog(Base, UUIDMixin, TimestampMixin):
    """작업 로그"""
    __tablename__ = "job_logs"

    # 작업 정보
    job_type: Mapped[JobType] = mapped_column(SQLEnum(JobType), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), nullable=True
    )

    # 상태
    status: Mapped[JobStatus] = mapped_column(
        SQLEnum(JobStatus), default=JobStatus.PENDING
    )

    # 시간
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 결과
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # 메타
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 인덱스
    __table_args__ = (
        Index("idx_job_type_status", "job_type", "status"),
        Index("idx_job_channel", "channel_id"),
    )
```

---

## 3. 마이그레이션 설정 (Alembic)

```python
# alembic/env.py
from app.models import Base
from app.config import settings

target_metadata = Base.metadata

def run_migrations_online():
    connectable = create_engine(settings.database_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()
```

---

## 4. 인덱스 전략 요약

| 테이블 | 인덱스 | 용도 |
|--------|--------|------|
| topics | channel_id + status | 채널별 대기 주제 조회 |
| topics | score_total | 점수순 정렬 |
| topics | content_hash | 중복 체크 |
| scripts | channel_id + status | 채널별 검수 대기 |
| videos | channel_id + status | 채널별 영상 상태 |
| uploads | scheduled_at | 예약 업로드 조회 |
| performances | views | 성과순 정렬 |
| review_queue | status + priority | 검수 우선순위 |

---

## 5. Redis 스키마

```python
# 키 네이밍 컨벤션
REDIS_KEYS = {
    # 중복 체크 캐시 (24시간 TTL)
    "topic_hash": "topic:hash:{hash}",

    # 채널별 최근 업로드 시간
    "channel_last_upload": "channel:{channel_id}:last_upload",

    # 일일 업로드 카운트
    "channel_daily_count": "channel:{channel_id}:daily:{date}",

    # 검수 대기 알림 (Set)
    "review_pending": "review:pending:{channel_id}",

    # 작업 상태
    "job_status": "job:{job_id}:status",

    # 시간 분석 캐시 (1일 TTL)
    "time_analysis": "analytics:time:{channel_id}",
}
```
