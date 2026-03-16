"""Unit tests for dependency factory functions."""

from unittest.mock import MagicMock

from app.core.dependencies import (
    create_http_client,
    create_llm_client,
    create_normalizer,
    create_prompt_manager,
    create_script_generator,
    get_session_factory,
)


class TestSessionFactory:
    """Tests for get_session_factory."""

    def test_returns_callable(self) -> None:
        """Test that session factory returns a callable."""
        factory = get_session_factory()
        assert callable(factory)


class TestCreateHttpClient:
    """Tests for create_http_client."""

    def test_creates_http_client(self) -> None:
        """Test HTTP client creation."""
        client = create_http_client()
        assert client is not None


class TestCreateLLMClient:
    """Tests for create_llm_client."""

    def test_creates_llm_client(self) -> None:
        """Test LLM client creation."""
        client = create_llm_client()
        assert client is not None


class TestCreatePromptManager:
    """Tests for create_prompt_manager."""

    def test_creates_prompt_manager(self) -> None:
        """Test prompt manager creation."""
        pm = create_prompt_manager()
        assert pm is not None


class TestCreateScriptGenerator:
    """Tests for create_script_generator."""

    def test_creates_with_defaults(self) -> None:
        """Test script generator creation with defaults."""
        generator = create_script_generator()
        assert generator is not None

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
        assert normalizer is not None

    def test_creates_with_injected_deps(self) -> None:
        """Test normalizer creation with injected dependencies."""
        llm = MagicMock()
        pm = MagicMock()
        normalizer = create_normalizer(llm_client=llm, prompt_manager=pm)
        assert normalizer is not None
