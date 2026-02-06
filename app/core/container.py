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
    async def endpoint(redis: Redis = Depends(container.redis)):
        ...

    # In Celery
    from app.core.container import container

    @celery_app.task
    def my_task():
        with container.reset_singletons():  # Or use scoped context
            redis = container.redis()
            ...

    # In tests
    with container.redis.override(mock_redis):
        ...
"""

from dependency_injector import containers, providers
from redis import Redis as SyncRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Config, get_config


class InfrastructureContainer(containers.DeclarativeContainer):
    """Infrastructure layer dependencies (databases, caches, external clients).

    These are typically Singleton or have special lifecycle management.
    """

    global_config = providers.Dependency(instance_of=Config)

    # ============================================
    # Redis
    # ============================================

    redis_async_client = providers.Singleton(
        Redis.from_url,
        url=global_config.provided.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
    )

    redis_sync_client = providers.Singleton(
        SyncRedis.from_url,
        url=global_config.provided.redis_url,
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
        url=global_config.provided.database_url,
        echo=global_config.provided.debug,
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
    # BM25 Search (ParadeDB pg_search)
    # ============================================

    bm25_search = providers.Singleton(
        "app.infrastructure.bm25_search.BM25Search",
        db_session_factory=db_session_factory,
    )

    # ============================================
    # LLM Clients
    # ============================================

    # Unified LLM client (LiteLLM-based, provider-agnostic)
    llm_client = providers.Singleton(
        "app.infrastructure.llm.LLMClient",
    )

    # ============================================
    # HTTP Client
    # ============================================

    http_client = providers.Singleton(
        "app.infrastructure.http_client.HTTPClient",
    )

    # ============================================
    # Prompt Manager
    # ============================================

    prompt_manager = providers.Singleton(
        "app.prompts.manager.PromptManager",
    )

    # ============================================
    # FFmpeg Wrapper
    # ============================================

    ffmpeg_wrapper = providers.Singleton(
        "app.services.generator.ffmpeg.FFmpegWrapper",
    )

    # ============================================
    # YouTube API Infrastructure
    # ============================================

    youtube_auth = providers.Singleton(
        "app.infrastructure.youtube_auth.YouTubeAuthClient",
        credentials_path=global_config.provided.youtube_credentials_path,
        token_path=global_config.provided.youtube_token_path,
    )

    youtube_api = providers.Singleton(
        "app.infrastructure.youtube_api.YouTubeAPIClient",
        auth_client=youtube_auth,
    )


class ConfigContainer(containers.DeclarativeContainer):
    """Configuration models container.

    Provides typed Pydantic config models for services.
    Configs are Singleton by default - loaded once and reused.
    """

    # Collector configs - can be overridden per channel
    filtering_config = providers.Singleton(
        "app.config.filtering.FilteringConfig",
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
    # Research configs
    # ============================================

    research_config = providers.Singleton(
        "app.config.research.ResearchConfig",
    )

    enrichment_config = providers.Singleton(
        "app.config.enrichment.EnrichmentConfig",
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
        "app.config.video.TTSProviderConfig",
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

    bgm_config = providers.Singleton(
        "app.config.bgm.BGMConfig",
    )

    # ============================================
    # YouTube Upload & Analytics configs
    # ============================================

    schedule_preference_config = providers.Singleton(
        "app.config.youtube_upload.SchedulePreferenceConfig",
    )

    youtube_api_config = providers.Singleton(
        "app.config.youtube_upload.YouTubeAPIConfig",
    )

    analytics_config = providers.Singleton(
        "app.config.youtube_upload.AnalyticsConfig",
    )

    youtube_upload_pipeline_config = providers.Singleton(
        "app.config.youtube_upload.YouTubeUploadPipelineConfig",
    )


class ServiceContainer(containers.DeclarativeContainer):
    """Service layer dependencies.

    Services are typically Transient (Factory) or Scoped.
    They receive infrastructure dependencies via injection.
    """

    global_config = providers.Dependency(instance_of=Config)
    infrastructure = providers.DependenciesContainer()
    configs = providers.DependenciesContainer()

    # ============================================
    # Video Template Loader
    # ============================================

    video_template_loader = providers.Singleton(
        "app.core.template_loader.VideoTemplateLoader",
    )

    # ============================================
    # ASS Subtitle Template Loader
    # ============================================

    ass_template_loader = providers.Singleton(
        "app.services.generator.templates.ASSTemplateLoader",
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
        llm_client=infrastructure.llm_client,
        prompt_manager=infrastructure.prompt_manager,
    )

    topic_filter = providers.Factory(
        "app.services.collector.filter.TopicFilter",
        config=configs.topic_filter_config,
    )

    series_matcher = providers.Factory(
        "app.services.collector.series_matcher.SeriesMatcher",
        config=configs.series_matcher_config,
    )

    global_topic_pool = providers.Factory(
        "app.services.collector.global_pool.GlobalTopicPool",
        redis=infrastructure.redis_async_client,
    )

    scoped_source_cache = providers.Factory(
        "app.services.collector.global_pool.ScopedSourceCache",
        redis=infrastructure.redis_async_client,
    )

    topic_collection_pipeline = providers.Factory(
        "app.services.collector.pipeline.TopicCollectionPipeline",
        session=infrastructure.db_session,
        http_client=infrastructure.http_client,
        normalizer=topic_normalizer,
        redis=infrastructure.redis_async_client,
        deduplicator=topic_deduplicator,
        scorer=topic_scorer,
        global_pool=global_topic_pool,
        scoped_cache=scoped_source_cache,
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
        prompt_manager=infrastructure.prompt_manager,
        bm25_search=infrastructure.bm25_search,
        llm_client=infrastructure.llm_client,
    )

    rag_reranker = providers.Factory(
        "app.services.rag.reranker.RAGReranker",
        config=configs.retrieval_config,
    )

    content_classifier = providers.Factory(
        "app.services.rag.classifier.ContentClassifier",
        llm_client=infrastructure.llm_client,
        prompt_manager=infrastructure.prompt_manager,
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
        prompt_manager=infrastructure.prompt_manager,
    )

    script_generator = providers.Factory(
        "app.services.rag.generator.ScriptGenerator",
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        chunker=script_chunker,
        embedder=content_embedder,
        vector_db=infrastructure.vector_db,
        llm_client=infrastructure.llm_client,
        prompt_manager=infrastructure.prompt_manager,
        db_session_factory=infrastructure.db_session_factory,
        config=configs.generation_config,
        quality_config=configs.quality_check_config,
    )

    # RAG Facade - groups related RAG services for simplified DI
    # Note: RAGFacade is a dataclass, instantiate directly with pre-configured components
    rag_facade = providers.Factory(
        "app.services.rag.facade.RAGFacade",
        retriever=rag_retriever,
        embedder=content_embedder,
        context_builder=context_builder,
        prompt_builder=prompt_builder,
        chunker=script_chunker,
        quality_checker=providers.Factory(
            "app.services.rag.quality.ScriptQualityChecker",
            config=configs.quality_check_config,
        ),
        llm_client=infrastructure.llm_client,
        prompt_manager=infrastructure.prompt_manager,
    )

    # ============================================
    # Research & Enrichment Services
    # ============================================

    cluster_enricher = providers.Factory(
        "app.services.collector.cluster_enricher.ClusterEnricher",
        llm_client=infrastructure.llm_client,
        prompt_manager=infrastructure.prompt_manager,
    )

    tavily_client = providers.Singleton(
        "app.services.research.tavily.TavilyClient",
        api_key=global_config.provided.tavily_api_key,
        http_client=infrastructure.http_client,
        config=configs.research_config,
    )

    research_query_builder = providers.Factory(
        "app.services.research.query_builder.ResearchQueryBuilder",
        llm_client=infrastructure.llm_client,
        prompt_manager=infrastructure.prompt_manager,
    )

    enriched_pipeline = providers.Factory(
        "app.services.pipeline.enriched_generation.EnrichedGenerationPipeline",
        cluster_enricher=cluster_enricher,
        research_client=tavily_client,
        query_builder=research_query_builder,
        context_builder=context_builder,
        script_generator=script_generator,
        db_session_factory=infrastructure.db_session_factory,
    )

    # ============================================
    # Video Generation Services
    # ============================================

    # TTS Services
    tts_factory = providers.Factory(
        "app.services.generator.tts.factory.TTSEngineFactory",
        ffmpeg_wrapper=infrastructure.ffmpeg_wrapper,
        config=configs.tts_config,
        elevenlabs_api_key=global_config.provided.elevenlabs_api_key,
    )

    # Visual Sourcing Services
    pexels_client = providers.Singleton(
        "app.services.generator.visual.pexels.PexelsClient",
        api_key=global_config.provided.pexels_api_key,
    )

    pixabay_client = providers.Singleton(
        "app.services.generator.visual.pixabay.PixabayClient",
        api_key=global_config.provided.pixabay_api_key,
    )

    dalle_generator = providers.Singleton(
        "app.services.generator.visual.dall_e.DALLEGenerator",
        api_key=global_config.provided.openai_api_key,
    )

    sd_generator = providers.Singleton(
        "app.services.generator.visual.stable_diffusion.StableDiffusionGenerator",
        http_client=infrastructure.http_client,
    )

    tavily_image_client = providers.Singleton(
        "app.services.generator.visual.tavily_image.TavilyImageClient",
        tavily_client=tavily_client,
        http_client=infrastructure.http_client,
        sd_generator=sd_generator,
    )

    fallback_generator = providers.Factory(
        "app.services.generator.visual.fallback.FallbackGenerator",
    )

    visual_manager = providers.Factory(
        "app.services.generator.visual.manager.VisualSourcingManager",
        http_client=infrastructure.http_client,
        config=configs.visual_config,
        pexels_client=pexels_client,
        pixabay_client=pixabay_client,
        tavily_image_client=tavily_image_client,
        dalle_generator=dalle_generator,
        sd_generator=sd_generator,
        fallback_generator=fallback_generator,
    )

    # Subtitle Generator
    subtitle_generator = providers.Factory(
        "app.services.generator.subtitle.SubtitleGenerator",
        config=configs.subtitle_config,
        composition_config=configs.composition_config,
        template_loader=ass_template_loader,
    )

    # FFmpeg Compositor
    ffmpeg_compositor = providers.Factory(
        "app.services.generator.compositor.FFmpegCompositor",
        ffmpeg_wrapper=infrastructure.ffmpeg_wrapper,
        config=configs.composition_config,
    )

    # BGM Services
    bgm_downloader = providers.Factory(
        "app.services.generator.bgm.downloader.BGMDownloader",
        config=configs.bgm_config,
    )

    bgm_manager = providers.Factory(
        "app.services.generator.bgm.manager.BGMManager",
        config=configs.bgm_config,
        downloader=bgm_downloader,
    )

    # Video Pipeline (Orchestrator)
    video_pipeline = providers.Factory(
        "app.services.generator.pipeline.VideoGenerationPipeline",
        tts_factory=tts_factory,
        visual_manager=visual_manager,
        subtitle_generator=subtitle_generator,
        compositor=ffmpeg_compositor,
        ffmpeg_wrapper=infrastructure.ffmpeg_wrapper,
        db_session_factory=infrastructure.db_session_factory,
        config=configs.video_generation_config,
        template_loader=video_template_loader,
        bgm_manager=bgm_manager,
    )

    # ============================================
    # YouTube Upload & Analytics Services
    # ============================================

    youtube_uploader = providers.Factory(
        "app.services.uploader.youtube_uploader.YouTubeUploader",
        youtube_api=infrastructure.youtube_api,
        db_session_factory=infrastructure.db_session_factory,
    )

    optimal_time_analyzer = providers.Factory(
        "app.services.analytics.optimal_time.OptimalTimeAnalyzer",
        db_session_factory=infrastructure.db_session_factory,
        config=configs.analytics_config,
    )

    upload_scheduler = providers.Factory(
        "app.services.scheduler.upload_scheduler.UploadScheduler",
        db_session_factory=infrastructure.db_session_factory,
        config=configs.schedule_preference_config,
        optimal_time_analyzer=optimal_time_analyzer,
    )

    analytics_collector = providers.Factory(
        "app.services.analytics.collector.YouTubeAnalyticsCollector",
        youtube_api=infrastructure.youtube_api,
        db_session_factory=infrastructure.db_session_factory,
        config=configs.analytics_config,
    )

    upload_pipeline = providers.Factory(
        "app.services.uploader.pipeline.UploadPipeline",
        uploader=youtube_uploader,
        db_session_factory=infrastructure.db_session_factory,
        config=configs.youtube_upload_pipeline_config,
    )


class ApplicationContainer(containers.DeclarativeContainer):
    """Root application container.

    Composes all sub-containers and provides the main entry point.
    """

    # Global Config singleton (environment variables)
    # Uses get_config() to ensure same instance across the app
    config = providers.Singleton(get_config)

    # Sub-containers
    infrastructure = providers.Container(
        InfrastructureContainer,
        global_config=config,
    )

    configs = providers.Container(
        ConfigContainer,
    )

    services = providers.Container(
        ServiceContainer,
        global_config=config,
        infrastructure=infrastructure,
        configs=configs,
    )

    # ============================================
    # Essential Convenience Accessors
    # ============================================
    # Only keep the most commonly used accessors.
    # For other services, use container.services.* or container.infrastructure.*

    # Redis - frequently used directly
    redis = providers.Singleton(
        lambda client: client,
        client=infrastructure.redis_async_client,
    )

    redis_sync = providers.Singleton(
        lambda client: client,
        client=infrastructure.redis_sync_client,
    )

    # Database session - frequently used directly
    db_session = providers.Factory(
        lambda session: session,
        session=infrastructure.db_session,
    )


def create_container() -> ApplicationContainer:
    """Create and configure the application container.

    Returns:
        Configured ApplicationContainer instance
    """
    return ApplicationContainer()


# Global container instance
container = create_container()


# ============================================
# Configuration Validation
# ============================================


def validate_configs() -> list[str]:
    """Validate all configuration models on application startup.

    Forces loading of all config providers and catches validation errors.
    Call this during application startup (e.g., in FastAPI lifespan).

    Returns:
        List of validation error messages. Empty list means all configs are valid.

    Example:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            errors = validate_configs()
            if errors:
                logger.error(f"Config validation failed: {errors}")
                raise RuntimeError("Invalid configuration")
            yield
    """
    errors: list[str] = []

    # Validate config container providers
    for name in dir(container.configs):
        if name.startswith("_"):
            continue
        try:
            provider = getattr(container.configs, name, None)
            if provider is not None and callable(provider):
                # Force provider resolution
                provider()
        except Exception as e:
            errors.append(f"configs.{name}: {str(e)}")

    return errors


# ============================================
# FastAPI Integration
# ============================================


def get_container() -> ApplicationContainer:
    """Get the global container (for FastAPI Depends)."""
    return container


# get_config is re-exported from app.core.config for convenience


async def get_redis() -> Redis:
    """FastAPI dependency for async Redis client."""
    return container.redis()


def get_redis_sync() -> SyncRedis:
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
    how FastAPI creates a request scope. Provides:
    - Task-scoped DB session (closed on exit)
    - Access to singleton infrastructure services
    - Access to service factories

    Usage:
        @celery_app.task
        def my_task():
            with TaskScope() as scope:
                redis = scope.redis()
                deduplicator = scope.deduplicator()
                ...

        # For async tasks:
        async with TaskScope() as scope:
            async with scope.db_session() as session:
                ...

    Attributes:
        infrastructure: Access to infrastructure services (redis, db_engine, etc.)
        services: Access to service factories
        configs: Access to configuration models
    """

    def __init__(self) -> None:
        self._container: ApplicationContainer | None = None
        self._sessions: list[AsyncSession] = []

    @property
    def infrastructure(self) -> InfrastructureContainer:
        """Access infrastructure services."""
        if not self._container:
            raise RuntimeError("TaskScope not entered")
        return self._container.infrastructure

    @property
    def services(self) -> ServiceContainer:
        """Access service factories."""
        if not self._container:
            raise RuntimeError("TaskScope not entered")
        return self._container.services

    @property
    def configs(self) -> ConfigContainer:
        """Access configuration models."""
        if not self._container:
            raise RuntimeError("TaskScope not entered")
        return self._container.configs

    def redis(self) -> Redis:
        """Get async Redis client."""
        if not self._container:
            raise RuntimeError("TaskScope not entered")
        return self._container.redis()

    def db_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get DB session factory for creating scoped sessions."""
        if not self._container:
            raise RuntimeError("TaskScope not entered")
        return self._container.db_session_factory()

    def __enter__(self) -> "TaskScope":
        self._container = container
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Note: In sync context, async sessions should be managed
        # by the caller using asyncio.run() or similar
        self._container = None
        return None

    async def __aenter__(self) -> "TaskScope":
        self._container = container
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        import contextlib

        # Close any sessions that were tracked
        for session in self._sessions:
            with contextlib.suppress(Exception):
                await session.close()
        self._sessions.clear()
        self._container = None
        return None


# ============================================
# Testing Utilities
# ============================================


def override_redis(mock_redis: Redis):
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
    "get_config",
    "get_container",
    "get_db_session",
    "get_redis",
    "get_redis_sync",
    "override_db_session",
    "override_redis",
    "TaskScope",
    "validate_configs",
]
