"""Dependency Injection Container.

This module provides a centralized DI container using dependency-injector.
Supports ASP.NET Core-style lifecycles:
- Singleton: One instance for the entire application
- Scoped: One instance per request/task (FastAPI request or Celery task)
- Transient: New instance every time (Factory)

Usage:
    # In FastAPI
    from app.core.container import container

    @app.get("/")
    async def endpoint(redis: AsyncRedis = Depends(container.redis_client)):
        ...

    # In Celery
    from app.core.container import container

    @celery_app.task
    def my_task():
        with container.reset_singletons():  # Or use scoped context
            redis = container.redis_client()
            ...

    # In tests
    with container.redis_client.override(mock_redis):
        ...
"""

from dependency_injector import containers, providers
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


class InfrastructureContainer(containers.DeclarativeContainer):
    """Infrastructure layer dependencies (databases, caches, external clients).

    These are typically Singleton or have special lifecycle management.
    """

    config = providers.Configuration()

    # ============================================
    # Redis
    # ============================================

    redis_async_client = providers.Singleton(
        AsyncRedis.from_url,
        url=config.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
    )

    redis_sync_client = providers.Singleton(
        Redis.from_url,
        url=config.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
    )

    # ============================================
    # Database
    # ============================================

    db_engine = providers.Singleton(
        create_async_engine,
        url=config.database_url,
        echo=config.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    db_session_factory = providers.Singleton(
        async_sessionmaker,
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Scoped session - new session per request/task
    db_session = providers.Factory(
        lambda factory: factory(),
        factory=db_session_factory,
    )

    # ============================================
    # Vector DB (pgvector)
    # ============================================

    vector_db = providers.Singleton(
        "app.infrastructure.pgvector_db.PgVectorDB",
        db_session_factory=db_session_factory,
        model_name="BAAI/bge-m3",
        device="cpu",
    )

    # ============================================
    # LLM Clients
    # ============================================

    anthropic_client = providers.Singleton(
        "anthropic.AsyncAnthropic",
        api_key=config.anthropic_api_key,
    )

    # Unified LLM client (LiteLLM-based, provider-agnostic)
    llm_client = providers.Singleton(
        "app.infrastructure.llm.LLMClient",
    )


class ConfigContainer(containers.DeclarativeContainer):
    """Configuration models container.

    Provides typed Pydantic config models for services.
    Configs are Singleton by default - loaded once and reused.
    """

    # Collector configs - can be overridden per channel
    topic_filter_config = providers.Singleton(
        "app.config.filtering.TopicFilterConfig",
    )

    series_matcher_config = providers.Singleton(
        "app.config.series.SeriesMatcherConfig",
    )

    scoring_config = providers.Singleton(
        "app.config.content.ScoringConfig",
    )

    queue_config = providers.Singleton(
        "app.config.content.QueueConfig",
    )

    dedup_config = providers.Singleton(
        "app.config.content.DedupConfig",
    )

    # Source configs - typed defaults for each source type
    hackernews_config = providers.Singleton(
        "app.config.sources.HackerNewsConfig",
    )

    reddit_config = providers.Singleton(
        "app.config.sources.RedditConfig",
    )

    rss_config = providers.Singleton(
        "app.config.sources.RSSConfig",
    )

    google_trends_config = providers.Singleton(
        "app.config.sources.GoogleTrendsConfig",
    )

    youtube_trending_config = providers.Singleton(
        "app.config.sources.YouTubeTrendingConfig",
    )

    web_scraper_config = providers.Singleton(
        "app.config.sources.WebScraperConfig",
    )

    # ============================================
    # RAG configs
    # ============================================

    rag_config = providers.Singleton(
        "app.config.rag.RAGConfig",
    )

    embedding_config = providers.Singleton(
        "app.config.rag.EmbeddingConfig",
    )

    retrieval_config = providers.Singleton(
        "app.config.rag.RetrievalConfig",
    )

    query_expansion_config = providers.Singleton(
        "app.config.rag.QueryExpansionConfig",
    )

    chunking_config = providers.Singleton(
        "app.config.rag.ChunkingConfig",
    )

    quality_check_config = providers.Singleton(
        "app.config.rag.QualityCheckConfig",
    )

    generation_config = providers.Singleton(
        "app.config.rag.GenerationConfig",
    )

    # ============================================
    # Video Generation configs
    # ============================================

    video_generation_config = providers.Singleton(
        "app.config.video.VideoGenerationConfig",
    )

    tts_config = providers.Singleton(
        "app.config.video.TTSConfig",
    )

    subtitle_config = providers.Singleton(
        "app.config.video.SubtitleConfig",
    )

    visual_config = providers.Singleton(
        "app.config.video.VisualConfig",
    )

    composition_config = providers.Singleton(
        "app.config.video.CompositionConfig",
    )

    thumbnail_config = providers.Singleton(
        "app.config.video.ThumbnailConfig",
    )


class ServiceContainer(containers.DeclarativeContainer):
    """Service layer dependencies.

    Services are typically Transient (Factory) or Scoped.
    They receive infrastructure dependencies via injection.
    """

    config = providers.Configuration()
    infrastructure = providers.DependenciesContainer()
    configs = providers.DependenciesContainer()

    # ============================================
    # Video Template Loader
    # ============================================

    video_template_loader = providers.Singleton(
        "app.core.template_loader.VideoTemplateLoader",
    )

    # ============================================
    # Collector Services
    # ============================================

    topic_deduplicator = providers.Factory(
        "app.services.collector.deduplicator.TopicDeduplicator",
        redis=infrastructure.redis_async_client,
        config=configs.dedup_config,
    )

    topic_scorer = providers.Factory(
        "app.services.collector.scorer.TopicScorer",
        config=configs.scoring_config,
    )

    topic_queue_manager = providers.Factory(
        "app.services.collector.queue_manager.TopicQueueManager",
        redis=infrastructure.redis_async_client,
        config=configs.queue_config,
    )

    topic_normalizer = providers.Factory(
        "app.services.collector.normalizer.TopicNormalizer",
    )

    topic_filter = providers.Factory(
        "app.services.collector.filter.TopicFilter",
        config=configs.topic_filter_config,
    )

    series_matcher = providers.Factory(
        "app.services.collector.series_matcher.SeriesMatcher",
        config=configs.series_matcher_config,
    )

    # ============================================
    # RAG Services
    # ============================================

    content_embedder = providers.Factory(
        "app.services.rag.embedder.ContentEmbedder",
        vector_db=infrastructure.vector_db,
        config=configs.embedding_config,
    )

    rag_retriever = providers.Factory(
        "app.services.rag.retriever.SpecializedRetriever",
        vector_db=infrastructure.vector_db,
        db_session_factory=infrastructure.db_session_factory,
        retrieval_config=configs.retrieval_config,
        query_config=configs.query_expansion_config,
        llm_client=infrastructure.anthropic_client,
    )

    rag_reranker = providers.Factory(
        "app.services.rag.reranker.RAGReranker",
        config=configs.retrieval_config,
    )

    content_classifier = providers.Factory(
        "app.services.rag.classifier.ContentClassifier",
        llm_client=infrastructure.llm_client,
        model="anthropic/claude-3-5-haiku-20241022",
    )

    script_chunker = providers.Factory(
        "app.services.rag.chunker.ScriptChunker",
        config=configs.chunking_config,
        llm_classifier=content_classifier,
    )

    context_builder = providers.Factory(
        "app.services.rag.context.ContextBuilder",
        retriever=rag_retriever,
        db_session_factory=infrastructure.db_session_factory,
    )

    prompt_builder = providers.Factory(
        "app.services.rag.prompt.PromptBuilder",
    )

    script_generator = providers.Factory(
        "app.services.rag.generator.ScriptGenerator",
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        chunker=script_chunker,
        embedder=content_embedder,
        vector_db=infrastructure.vector_db,
        llm_client=infrastructure.llm_client,
        db_session_factory=infrastructure.db_session_factory,
        config=configs.generation_config,
        quality_config=configs.quality_check_config,
    )

    # ============================================
    # Video Generation Services
    # ============================================

    # TTS Services
    edge_tts_engine = providers.Singleton(
        "app.services.generator.tts.edge.EdgeTTSEngine",
    )

    elevenlabs_engine = providers.Singleton(
        "app.services.generator.tts.elevenlabs.ElevenLabsEngine",
        api_key=config.elevenlabs_api_key,
    )

    tts_factory = providers.Factory(
        "app.services.generator.tts.factory.TTSEngineFactory",
        config=configs.tts_config,
        elevenlabs_api_key=config.elevenlabs_api_key,
    )

    # Visual Sourcing Services
    pexels_client = providers.Singleton(
        "app.services.generator.visual.pexels.PexelsClient",
        api_key=config.pexels_api_key,
    )

    ai_image_generator = providers.Singleton(
        "app.services.generator.visual.ai_image.AIImageGenerator",
        api_key=config.openai_api_key,
        config=configs.visual_config,
    )

    fallback_generator = providers.Factory(
        "app.services.generator.visual.fallback.FallbackGenerator",
    )

    visual_manager = providers.Factory(
        "app.services.generator.visual.manager.VisualSourcingManager",
        config=configs.visual_config,
        pexels_client=pexels_client,
        ai_generator=ai_image_generator,
        fallback_generator=fallback_generator,
    )

    # Subtitle Generator
    subtitle_generator = providers.Factory(
        "app.services.generator.subtitle.SubtitleGenerator",
        config=configs.subtitle_config,
    )

    # FFmpeg Compositor
    ffmpeg_compositor = providers.Factory(
        "app.services.generator.compositor.FFmpegCompositor",
        config=configs.composition_config,
    )

    # Thumbnail Generator
    thumbnail_generator = providers.Factory(
        "app.services.generator.thumbnail.ThumbnailGenerator",
        config=configs.thumbnail_config,
    )

    # Video Pipeline (Orchestrator)
    video_pipeline = providers.Factory(
        "app.services.generator.pipeline.VideoGenerationPipeline",
        tts_factory=tts_factory,
        visual_manager=visual_manager,
        subtitle_generator=subtitle_generator,
        compositor=ffmpeg_compositor,
        thumbnail_generator=thumbnail_generator,
        db_session_factory=infrastructure.db_session_factory,
        config=configs.video_generation_config,
        template_loader=video_template_loader,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application container.

    Composes all sub-containers and provides the main entry point.
    """

    config = providers.Configuration()

    # Sub-containers
    infrastructure = providers.Container(
        InfrastructureContainer,
        config=config,
    )

    configs = providers.Container(
        ConfigContainer,
    )

    services = providers.Container(
        ServiceContainer,
        config=config,
        infrastructure=infrastructure,
        configs=configs,
    )

    # ============================================
    # Convenience accessors (shortcuts)
    # ============================================

    # Infrastructure
    redis = providers.Singleton(
        lambda client: client,
        client=infrastructure.redis_async_client,
    )

    redis_sync = providers.Singleton(
        lambda client: client,
        client=infrastructure.redis_sync_client,
    )

    db_session = providers.Factory(
        lambda session: session,
        session=infrastructure.db_session,
    )

    # Services
    deduplicator = providers.Factory(
        lambda svc: svc,
        svc=services.topic_deduplicator,
    )

    scorer = providers.Factory(
        lambda svc: svc,
        svc=services.topic_scorer,
    )

    queue_manager = providers.Factory(
        lambda svc: svc,
        svc=services.topic_queue_manager,
    )

    normalizer = providers.Factory(
        lambda svc: svc,
        svc=services.topic_normalizer,
    )

    topic_filter = providers.Factory(
        lambda svc: svc,
        svc=services.topic_filter,
    )

    series_matcher = providers.Factory(
        lambda svc: svc,
        svc=services.series_matcher,
    )

    # RAG Services
    embedder = providers.Factory(
        lambda svc: svc,
        svc=services.content_embedder,
    )

    retriever = providers.Factory(
        lambda svc: svc,
        svc=services.rag_retriever,
    )

    reranker = providers.Factory(
        lambda svc: svc,
        svc=services.rag_reranker,
    )

    chunker = providers.Factory(
        lambda svc: svc,
        svc=services.script_chunker,
    )

    generator = providers.Factory(
        lambda svc: svc,
        svc=services.script_generator,
    )

    # Video Generation Services
    tts_factory = providers.Factory(
        lambda svc: svc,
        svc=services.tts_factory,
    )

    visual_manager = providers.Factory(
        lambda svc: svc,
        svc=services.visual_manager,
    )

    subtitle_generator = providers.Factory(
        lambda svc: svc,
        svc=services.subtitle_generator,
    )

    compositor = providers.Factory(
        lambda svc: svc,
        svc=services.ffmpeg_compositor,
    )

    thumbnail_generator = providers.Factory(
        lambda svc: svc,
        svc=services.thumbnail_generator,
    )

    video_pipeline = providers.Factory(
        lambda svc: svc,
        svc=services.video_pipeline,
    )

    video_template_loader = providers.Singleton(
        lambda svc: svc,
        svc=services.video_template_loader,
    )


def create_container() -> ApplicationContainer:
    """Create and configure the application container.

    Returns:
        Configured ApplicationContainer instance
    """
    container = ApplicationContainer()

    # Wire configuration from settings
    container.config.from_dict(
        {
            "redis_url": str(settings.redis_url),
            "database_url": str(settings.database_url),
            "debug": settings.debug,
            "anthropic_api_key": settings.anthropic_api_key,
            # Video generation API keys
            "elevenlabs_api_key": settings.elevenlabs_api_key,
            "pexels_api_key": settings.pexels_api_key,
            "openai_api_key": settings.openai_api_key,
        }
    )

    return container


# Global container instance
container = create_container()


# ============================================
# FastAPI Integration
# ============================================


def get_container() -> ApplicationContainer:
    """Get the global container (for FastAPI Depends)."""
    return container


async def get_redis() -> AsyncRedis:
    """FastAPI dependency for async Redis client."""
    return container.redis()


def get_redis_sync() -> Redis:
    """Get sync Redis client."""
    return container.redis_sync()


async def get_db_session() -> AsyncSession:
    """FastAPI dependency for database session.

    Yields a session and ensures cleanup.
    """
    session = container.db_session()
    try:
        yield session
    finally:
        await session.close()


# ============================================
# Celery Integration
# ============================================


class TaskScope:
    """Context manager for Celery task scope.

    Creates a scoped context for a Celery task, similar to
    how FastAPI creates a request scope.

    Usage:
        @celery_app.task
        def my_task():
            with TaskScope() as scope:
                redis = scope.redis()
                deduplicator = scope.deduplicator()
                ...
    """

    def __init__(self) -> None:
        self._container: ApplicationContainer | None = None

    def __enter__(self) -> ApplicationContainer:
        # For now, just return the global container
        # In the future, we could create request-scoped overrides
        self._container = container
        return self._container

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cleanup if needed
        self._container = None
        return None


# ============================================
# Testing Utilities
# ============================================


def override_redis(mock_redis: AsyncRedis):
    """Context manager to override Redis for testing.

    Usage:
        with override_redis(mock_redis):
            # All Redis access will use mock_redis
            ...
    """
    return container.infrastructure.redis_async_client.override(mock_redis)


def override_db_session(mock_session: AsyncSession):
    """Context manager to override DB session for testing."""
    return container.infrastructure.db_session.override(mock_session)


__all__ = [
    "ApplicationContainer",
    "ConfigContainer",
    "InfrastructureContainer",
    "ServiceContainer",
    "container",
    "create_container",
    "get_container",
    "get_redis",
    "get_redis_sync",
    "get_db_session",
    "TaskScope",
    "override_redis",
    "override_db_session",
]
