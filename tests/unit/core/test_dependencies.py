"""Unit tests for dependency factory functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.dependencies import (
    close_singletons,
    create_analytics_collector,
    create_http_client,
    create_llm_client,
    create_normalizer,
    create_optimal_time_analyzer,
    create_prompt_manager,
    create_script_generator,
    create_upload_scheduler,
    get_session_factory,
    reset_singletons,
)
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.llm import LLMClient
from app.prompts.manager import PromptManager
from app.services.analytics.collector import YouTubeAnalyticsCollector
from app.services.analytics.optimal_time import OptimalTimeAnalyzer
from app.services.collector.normalizer import TopicNormalizer
from app.services.scheduler.upload_scheduler import UploadScheduler
from app.services.script_generator import ScriptGenerator


class TestSessionFactory:
    """Tests for get_session_factory."""

    def test_returns_callable(self) -> None:
        """Test that session factory returns a callable."""
        factory = get_session_factory()
        assert callable(factory)


class TestCreateHttpClient:
    """Tests for create_http_client."""

    def test_creates_http_client(self) -> None:
        """Test HTTP client creation returns correct type."""
        reset_singletons()
        client = create_http_client()
        assert isinstance(client, HTTPClient)

    def test_returns_singleton(self) -> None:
        """Test HTTP client returns same instance."""
        reset_singletons()
        client1 = create_http_client()
        client2 = create_http_client()
        assert client1 is client2


class TestCreateLLMClient:
    """Tests for create_llm_client."""

    def test_creates_llm_client(self) -> None:
        """Test LLM client creation returns correct type."""
        reset_singletons()
        client = create_llm_client()
        assert isinstance(client, LLMClient)

    def test_returns_singleton(self) -> None:
        """Test LLM client returns same instance."""
        reset_singletons()
        client1 = create_llm_client()
        client2 = create_llm_client()
        assert client1 is client2


class TestCreatePromptManager:
    """Tests for create_prompt_manager."""

    def test_creates_prompt_manager(self) -> None:
        """Test prompt manager creation returns correct type."""
        reset_singletons()
        pm = create_prompt_manager()
        assert isinstance(pm, PromptManager)


class TestCreateScriptGenerator:
    """Tests for create_script_generator."""

    def test_creates_with_defaults(self) -> None:
        """Test script generator creation with defaults."""
        generator = create_script_generator()
        assert isinstance(generator, ScriptGenerator)

    def test_creates_with_injected_deps(self) -> None:
        """Test script generator creation with injected dependencies."""
        llm = MagicMock()
        pm = MagicMock()
        generator = create_script_generator(llm_client=llm, prompt_manager=pm)
        assert generator.llm_client is llm
        assert generator.prompt_manager is pm


class TestCreateNormalizer:
    """Tests for create_normalizer."""

    def test_creates_with_defaults(self) -> None:
        """Test normalizer creation with defaults."""
        normalizer = create_normalizer()
        assert isinstance(normalizer, TopicNormalizer)

    def test_creates_with_injected_deps(self) -> None:
        """Test normalizer creation with injected dependencies."""
        llm = MagicMock()
        pm = MagicMock()
        normalizer = create_normalizer(llm_client=llm, prompt_manager=pm)
        assert normalizer.llm_client is llm
        assert normalizer.prompt_manager is pm


class TestCreateAnalyticsCollector:
    """Tests for create_analytics_collector."""

    def test_creates_with_youtube_api(self) -> None:
        """Test analytics collector creation with YouTube API."""
        mock_api = MagicMock()
        collector = create_analytics_collector(youtube_api=mock_api)
        assert isinstance(collector, YouTubeAnalyticsCollector)
        assert collector.youtube_api is mock_api


class TestCreateOptimalTimeAnalyzer:
    """Tests for create_optimal_time_analyzer."""

    def test_creates_instance(self) -> None:
        """Test optimal time analyzer creation."""
        analyzer = create_optimal_time_analyzer()
        assert isinstance(analyzer, OptimalTimeAnalyzer)


class TestCreateUploadScheduler:
    """Tests for create_upload_scheduler."""

    def test_creates_instance(self) -> None:
        """Test upload scheduler creation."""
        scheduler = create_upload_scheduler()
        assert isinstance(scheduler, UploadScheduler)


class TestCloseSingletons:
    """Tests for close_singletons."""

    @pytest.mark.asyncio
    async def test_closes_http_client(self) -> None:
        """Test that close_singletons closes HTTPClient before clearing."""
        reset_singletons()
        client = create_http_client()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            await close_singletons()
            mock_close.assert_awaited_once()

        # Singletons are cleared after close
        new_client = create_http_client()
        assert new_client is not client
        reset_singletons()

    @pytest.mark.asyncio
    async def test_no_error_when_no_singletons(self) -> None:
        """Test that close_singletons is safe when nothing is initialized."""
        reset_singletons()
        await close_singletons()  # Should not raise
