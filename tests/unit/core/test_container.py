"""Unit tests for Dependency Injection Container.

Tests cover:
- Container initialization and configuration
- Provider types (Singleton, Factory)
- Sub-container composition
- FastAPI integration helpers
- Celery TaskScope integration
- Testing utilities (overrides)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import (
    TaskScope,
    container,
    create_container,
    get_container,
    get_redis,
    get_redis_sync,
    override_db_session,
    override_redis,
)


class TestContainerCreation:
    """Tests for container creation and configuration."""

    def test_create_container_returns_container_with_providers(self) -> None:
        """Test that create_container returns a container with expected providers."""
        new_container = create_container()
        # Should have config provider
        assert hasattr(new_container, "config")
        # Should have infrastructure sub-container
        assert hasattr(new_container, "infrastructure")
        # Should have services sub-container
        assert hasattr(new_container, "services")

    def test_container_has_config(self) -> None:
        """Test that container has configuration wired."""
        new_container = create_container()
        # Config should be set from settings
        assert new_container.config.redis_url() is not None
        assert new_container.config.database_url() is not None

    def test_global_container_exists(self) -> None:
        """Test that global container is initialized."""
        assert container is not None
        # Should have expected providers
        assert hasattr(container, "infrastructure")
        assert hasattr(container, "services")


class TestInfrastructureContainer:
    """Tests for InfrastructureContainer."""

    def test_infrastructure_container_has_redis_providers(self) -> None:
        """Test that infrastructure container has Redis providers."""
        assert hasattr(container.infrastructure, "redis_async_client")
        assert hasattr(container.infrastructure, "redis_sync_client")

    def test_infrastructure_container_has_db_providers(self) -> None:
        """Test that infrastructure container has database providers."""
        assert hasattr(container.infrastructure, "db_engine")
        assert hasattr(container.infrastructure, "db_session_factory")
        assert hasattr(container.infrastructure, "db_session")


class TestServiceContainer:
    """Tests for ServiceContainer."""

    def test_service_container_has_collector_services(self) -> None:
        """Test that service container has collector service providers."""
        assert hasattr(container.services, "topic_deduplicator")
        assert hasattr(container.services, "topic_scorer")
        assert hasattr(container.services, "topic_queue_manager")
        assert hasattr(container.services, "topic_normalizer")


class TestConvenienceAccessors:
    """Tests for convenience accessor providers."""

    def test_redis_accessor_exists(self) -> None:
        """Test that redis convenience accessor exists."""
        assert hasattr(container, "redis")
        assert hasattr(container, "redis_sync")

    def test_db_session_accessor_exists(self) -> None:
        """Test that db_session convenience accessor exists."""
        assert hasattr(container, "db_session")

    def test_service_accessors_exist(self) -> None:
        """Test that service convenience accessors exist."""
        assert hasattr(container, "deduplicator")
        assert hasattr(container, "scorer")
        assert hasattr(container, "queue_manager")
        assert hasattr(container, "normalizer")


class TestGetContainer:
    """Tests for get_container function."""

    def test_get_container_returns_global_container(self) -> None:
        """Test that get_container returns the global container."""
        result = get_container()
        assert result is container


class TestGetRedis:
    """Tests for Redis dependency functions."""

    @pytest.mark.asyncio
    async def test_get_redis_returns_async_client(self) -> None:
        """Test that get_redis returns async Redis client."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with container.infrastructure.redis_async_client.override(mock_redis):
            result = await get_redis()
            assert result is mock_redis

    def test_get_redis_sync_returns_sync_client(self) -> None:
        """Test that get_redis_sync returns sync Redis client."""
        mock_redis = MagicMock()

        with container.infrastructure.redis_sync_client.override(mock_redis):
            result = get_redis_sync()
            assert result is mock_redis


class TestTaskScope:
    """Tests for Celery TaskScope context manager."""

    def test_task_scope_returns_container_on_enter(self) -> None:
        """Test that TaskScope returns container on enter."""
        with TaskScope() as scope:
            assert scope is container

    def test_task_scope_exits_cleanly(self) -> None:
        """Test that TaskScope exits without error."""
        scope = TaskScope()
        scope.__enter__()
        result = scope.__exit__(None, None, None)
        assert result is None

    def test_task_scope_can_access_services(self) -> None:
        """Test that services can be accessed within TaskScope."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with container.infrastructure.redis_async_client.override(mock_redis), TaskScope() as scope:
            # Should be able to access deduplicator
            deduplicator = scope.deduplicator()
            assert deduplicator is not None


class TestOverrideUtilities:
    """Tests for testing override utilities."""

    def test_override_redis_context_manager(self) -> None:
        """Test override_redis context manager."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with override_redis(mock_redis):
            # Inside override, should get mock
            result = container.infrastructure.redis_async_client()
            assert result is mock_redis

    def test_override_db_session_context_manager(self) -> None:
        """Test override_db_session context manager."""
        mock_session = AsyncMock(spec=AsyncSession)

        with override_db_session(mock_session):
            # Inside override, should get mock
            result = container.infrastructure.db_session()
            assert result is mock_session


class TestServiceInstantiation:
    """Tests for service instantiation through container."""

    def test_scorer_instantiation(self) -> None:
        """Test TopicScorer can be instantiated."""
        scorer = container.scorer()
        assert scorer is not None

    def test_normalizer_instantiation(self) -> None:
        """Test TopicNormalizer can be instantiated."""
        normalizer = container.normalizer()
        assert normalizer is not None

    def test_deduplicator_instantiation_with_mock_redis(self) -> None:
        """Test TopicDeduplicator instantiation with mock Redis."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with container.infrastructure.redis_async_client.override(mock_redis):
            deduplicator = container.deduplicator()
            assert deduplicator is not None
            assert deduplicator.redis is mock_redis

    def test_queue_manager_instantiation_with_mock_redis(self) -> None:
        """Test TopicQueueManager instantiation with mock Redis."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with container.infrastructure.redis_async_client.override(mock_redis):
            queue_manager = container.queue_manager()
            assert queue_manager is not None
            assert queue_manager.redis is mock_redis


class TestFactoryBehavior:
    """Tests for Factory provider behavior (new instance each time)."""

    def test_scorer_is_factory(self) -> None:
        """Test that scorer returns new instance each time."""
        scorer1 = container.scorer()
        scorer2 = container.scorer()
        # Factory should return different instances
        assert scorer1 is not scorer2

    def test_normalizer_is_factory(self) -> None:
        """Test that normalizer returns new instance each time."""
        normalizer1 = container.normalizer()
        normalizer2 = container.normalizer()
        assert normalizer1 is not normalizer2

    def test_deduplicator_is_factory(self) -> None:
        """Test that deduplicator returns new instance each time."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with container.infrastructure.redis_async_client.override(mock_redis):
            dedup1 = container.deduplicator()
            dedup2 = container.deduplicator()
            assert dedup1 is not dedup2


class TestSingletonBehavior:
    """Tests for Singleton provider behavior."""

    def test_redis_async_is_singleton(self) -> None:
        """Test that redis_async_client returns same instance."""
        mock_redis = AsyncMock(spec=AsyncRedis)

        with container.infrastructure.redis_async_client.override(mock_redis):
            redis1 = container.infrastructure.redis_async_client()
            redis2 = container.infrastructure.redis_async_client()
            # Singleton should return same instance
            assert redis1 is redis2


class TestContainerExports:
    """Tests for module exports."""

    def test_all_exports_exist(self) -> None:
        """Test that all expected exports are available."""
        from app.core import container as container_module

        expected_exports = [
            "ApplicationContainer",
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

        for export in expected_exports:
            assert hasattr(container_module, export), f"Missing export: {export}"
