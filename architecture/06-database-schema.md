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
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    USED = "used"
    EXPIRED = "expired"


class Topic(Base, UUIDMixin, TimestampMixin):
    """수집된 주제"""
    __tablename__ = "topics"
    
    # 채널 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )
    
    # 소스 연결
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id")
    )
    
    # 제목
    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    title_translated: Mapped[str] = mapped_column(Text, nullable=True)
    title_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    
    # 내용
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # 분류
    categories: Mapped[list] = mapped_column(ARRAY(String), default=list)
    keywords: Mapped[list] = mapped_column(ARRAY(String), default=list)
    entities: Mapped[dict] = mapped_column(JSONB, default=list)  # [{name, type, sentiment}]
    language: Mapped[str] = mapped_column(String(10), default="ko")
    
    # 점수
    score_source: Mapped[float] = mapped_column(Float, default=0)
    score_freshness: Mapped[float] = mapped_column(Float, default=0)
    score_trend: Mapped[float] = mapped_column(Float, default=0)
    score_relevance: Mapped[float] = mapped_column(Float, default=0)
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    
    # 상태
    status: Mapped[TopicStatus] = mapped_column(
        SQLEnum(TopicStatus), default=TopicStatus.PENDING
    )
    
    # 시간
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # 중복 체크용 해시
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # 시리즈 연결
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("series.id"), nullable=True
    )
    
    # 관계
    channel: Mapped["Channel"] = relationship(back_populates="topics")
    source: Mapped["Source"] = relationship()
    scripts: Mapped[list["Script"]] = relationship(back_populates="topic")
    series: Mapped["Series"] = relationship(back_populates="topics")
    
    # 인덱스
    __table_args__ = (
        Index("idx_topic_channel_status", "channel_id", "status"),
        Index("idx_topic_score", "score_total"),
        Index("idx_topic_hash", "content_hash"),
        Index("idx_topic_expires", "expires_at"),
    )
```

### 2.6 스크립트 (Script)
```python
class ScriptStatus(str, Enum):
    GENERATED = "generated"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    USED = "used"


class Script(Base, UUIDMixin, TimestampMixin):
    """생성된 스크립트"""
    __tablename__ = "scripts"
    
    # 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id")
    )
    
    # 스크립트 내용
    script_text: Mapped[str] = mapped_column(Text, nullable=False)
    script_version: Mapped[int] = mapped_column(Integer, default=1)
    
    # 생성 메타
    generation_model: Mapped[str] = mapped_column(String(50), nullable=True)
    generation_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    context_chunks_used: Mapped[int] = mapped_column(Integer, default=0)
    
    # 품질 체크
    quality_score_style: Mapped[float] = mapped_column(Float, nullable=True)
    quality_score_hook: Mapped[float] = mapped_column(Float, nullable=True)
    quality_issues: Mapped[list] = mapped_column(ARRAY(String), default=list)
    
    # 예상 길이
    estimated_duration: Mapped[float] = mapped_column(Float, nullable=True)  # 초
    word_count: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # 상태
    status: Mapped[ScriptStatus] = mapped_column(
        SQLEnum(ScriptStatus), default=ScriptStatus.GENERATED
    )
    
    # 검수
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(100), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, nullable=True)
    
    # 관계
    channel: Mapped["Channel"] = relationship(back_populates="scripts")
    topic: Mapped["Topic"] = relationship(back_populates="scripts")
    videos: Mapped[list["Video"]] = relationship(back_populates="script")
    
    # 인덱스
    __table_args__ = (
        Index("idx_script_channel_status", "channel_id", "status"),
    )
```

### 2.7 영상 (Video)
```python
class VideoStatus(str, Enum):
    GENERATING = "generating"
    GENERATED = "generated"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PUBLISHED = "published"
    FAILED = "failed"


class Video(Base, UUIDMixin, TimestampMixin):
    """생성된 영상"""
    __tablename__ = "videos"
    
    # 연결
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id")
    )
    
    # 파일 경로
    video_path: Mapped[str] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str] = mapped_column(String(500), nullable=True)
    audio_path: Mapped[str] = mapped_column(String(500), nullable=True)
    subtitle_path: Mapped[str] = mapped_column(String(500), nullable=True)
    
    # 영상 메타
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    resolution: Mapped[str] = mapped_column(String(20), default="1080x1920")
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # 생성 정보
    tts_service: Mapped[str] = mapped_column(String(50), nullable=True)
    visual_sources: Mapped[list] = mapped_column(ARRAY(String), default=list)
    
    # 상태
    status: Mapped[VideoStatus] = mapped_column(
        SQLEnum(VideoStatus), default=VideoStatus.GENERATING
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    
    # 검수
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(100), nullable=True)
    
    # 관계
    channel: Mapped["Channel"] = relationship(back_populates="videos")
    script: Mapped["Script"] = relationship(back_populates="videos")
    upload: Mapped["Upload"] = relationship(back_populates="video", uselist=False)
    
    # 인덱스
    __table_args__ = (
        Index("idx_video_channel_status", "channel_id", "status"),
    )
```

### 2.8 업로드 (Upload)
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

### 2.9 성과 (Performance)
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

### 2.10 시리즈 (Series)
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

### 2.11 검수 큐 (ReviewQueue)
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

### 2.12 콘텐츠 청크 (벡터 DB 참조용)
```python
class ContentChunk(Base, UUIDMixin, TimestampMixin):
    """콘텐츠 청크 (벡터 DB 참조)"""
    __tablename__ = "content_chunks"
    
    # 원본 연결
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id")
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )
    
    # 청크 정보
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_position: Mapped[str] = mapped_column(String(20), default="body")  # hook, body, conclusion
    
    # 특성
    is_opinion: Mapped[bool] = mapped_column(Boolean, default=False)
    is_example: Mapped[bool] = mapped_column(Boolean, default=False)
    is_analogy: Mapped[bool] = mapped_column(Boolean, default=False)
    keywords: Mapped[list] = mapped_column(ARRAY(String), default=list)
    
    # 벡터 DB ID
    vector_id: Mapped[str] = mapped_column(String(100), nullable=True)
    
    # 인덱스
    __table_args__ = (
        Index("idx_chunk_channel", "channel_id"),
        Index("idx_chunk_script", "script_id"),
    )
```

### 2.13 작업 로그 (JobLog)
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
