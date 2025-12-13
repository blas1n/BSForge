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


class ServiceContainer(containers.DeclarativeContainer):
    """Service layer dependencies.

    Services are typically Transient (Factory) or Scoped.
    They receive infrastructure dependencies via injection.
    """

    config = providers.Configuration()
    infrastructure = providers.DependenciesContainer()
    configs = providers.DependenciesContainer()

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
