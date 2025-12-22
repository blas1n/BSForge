"""Unit tests for LLMClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.llm import (
    LLMClient,
    LLMConfig,
    LLMError,
    LLMResponse,
)


class TestLLMConfig:
    """Test LLMConfig dataclass."""

    def test_default_values(self) -> None:
        """Should have correct default values."""
        config = LLMConfig(model="anthropic/claude-3-5-haiku-20241022")

        assert config.model == "anthropic/claude-3-5-haiku-20241022"
        assert config.max_tokens == 1000
        assert config.temperature == 0.7
        assert config.timeout == 60

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = LLMConfig(
            model="openai/gpt-4o",
            max_tokens=2000,
            temperature=0.5,
            timeout=120,
        )

        assert config.model == "openai/gpt-4o"
        assert config.max_tokens == 2000
        assert config.temperature == 0.5
        assert config.timeout == 120

    def test_from_prompt_settings(self) -> None:
        """Should create config from LLMSettings."""
        mock_settings = MagicMock()
        mock_settings.model = "anthropic/claude-3-5-sonnet-20241022"
        mock_settings.max_tokens = 1500
        mock_settings.temperature = 0.8

        config = LLMConfig.from_prompt_settings(mock_settings, timeout=90)

        assert config.model == "anthropic/claude-3-5-sonnet-20241022"
        assert config.max_tokens == 1500
        assert config.temperature == 0.8
        assert config.timeout == 90

    def test_from_prompt_settings_default_timeout(self) -> None:
        """Should use default timeout when not specified."""
        mock_settings = MagicMock()
        mock_settings.model = "anthropic/claude-3-5-haiku-20241022"
        mock_settings.max_tokens = 500
        mock_settings.temperature = 0.3

        config = LLMConfig.from_prompt_settings(mock_settings)

        assert config.timeout == 60


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_basic_response(self) -> None:
        """Should store response data correctly."""
        response = LLMResponse(
            content="Hello, world!",
            model="anthropic/claude-3-5-haiku-20241022",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        assert response.content == "Hello, world!"
        assert response.model == "anthropic/claude-3-5-haiku-20241022"
        assert response.usage["total_tokens"] == 15
        assert response.raw_response is None

    def test_response_with_raw(self) -> None:
        """Should store raw response."""
        raw = {"id": "msg_123", "type": "message"}
        response = LLMResponse(
            content="Test",
            model="test-model",
            usage={},
            raw_response=raw,
        )

        assert response.raw_response == raw


class TestLLMClient:
    """Test LLMClient functionality."""

    @pytest.fixture
    def mock_acompletion(self) -> MagicMock:
        """Create mock for litellm.acompletion."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated response"
        mock_response.model = "anthropic/claude-3-5-haiku-20241022"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30

        return mock_response

    @pytest.fixture
    def llm_client(self) -> LLMClient:
        """Create LLMClient instance."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return LLMClient()

    def test_init(self) -> None:
        """Should initialize without error."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = LLMClient()
            assert client is not None

    @pytest.mark.asyncio
    async def test_complete_basic(self, llm_client: LLMClient, mock_acompletion: MagicMock) -> None:
        """Should complete request and return response."""
        with patch(
            "app.infrastructure.llm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_acompletion,
        ):
            config = LLMConfig(model="anthropic/claude-3-5-haiku-20241022")
            messages = [{"role": "user", "content": "Hello"}]

            response = await llm_client.complete(config, messages)

            assert response.content == "Generated response"
            assert response.model == "anthropic/claude-3-5-haiku-20241022"
            assert response.usage["prompt_tokens"] == 10
            assert response.usage["completion_tokens"] == 20
            assert response.usage["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_complete_passes_config(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should pass config parameters to acompletion."""
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            config = LLMConfig(
                model="openai/gpt-4o",
                max_tokens=2000,
                temperature=0.5,
                timeout=120,
            )
            messages = [{"role": "user", "content": "Test"}]

            await llm_client.complete(config, messages)

            mock_fn.assert_called_once_with(
                model="openai/gpt-4o",
                messages=messages,
                max_tokens=2000,
                temperature=0.5,
                timeout=120,
            )

    @pytest.mark.asyncio
    async def test_complete_with_kwargs(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should pass additional kwargs to acompletion."""
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            config = LLMConfig(model="anthropic/claude-3-5-haiku-20241022")
            messages = [{"role": "user", "content": "Test"}]

            await llm_client.complete(config, messages, stop=["END"], top_p=0.9)

            call_kwargs = mock_fn.call_args[1]
            assert call_kwargs["stop"] == ["END"]
            assert call_kwargs["top_p"] == 0.9

    @pytest.mark.asyncio
    async def test_complete_handles_empty_content(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should handle empty content in response."""
        mock_acompletion.choices[0].message.content = None

        with patch(
            "app.infrastructure.llm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_acompletion,
        ):
            config = LLMConfig(model="anthropic/claude-3-5-haiku-20241022")
            response = await llm_client.complete(config, [{"role": "user", "content": "Hi"}])

            assert response.content == ""

    @pytest.mark.asyncio
    async def test_complete_handles_no_usage(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should handle missing usage data."""
        mock_acompletion.usage = None

        with patch(
            "app.infrastructure.llm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_acompletion,
        ):
            config = LLMConfig(model="anthropic/claude-3-5-haiku-20241022")
            response = await llm_client.complete(config, [{"role": "user", "content": "Hi"}])

            assert response.usage == {}

    @pytest.mark.asyncio
    async def test_complete_raises_llm_error(self, llm_client: LLMClient) -> None:
        """Should wrap exceptions in LLMError."""
        with patch(
            "app.infrastructure.llm.acompletion",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            config = LLMConfig(model="anthropic/claude-3-5-haiku-20241022")

            with pytest.raises(LLMError) as exc_info:
                await llm_client.complete(config, [{"role": "user", "content": "Hi"}])

            assert "API error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_complete_simple(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should provide simplified completion interface."""
        with patch(
            "app.infrastructure.llm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_acompletion,
        ):
            result = await llm_client.complete_simple(
                model="anthropic/claude-3-5-haiku-20241022",
                prompt="Hello",
                max_tokens=500,
                temperature=0.3,
            )

            assert result == "Generated response"

    @pytest.mark.asyncio
    async def test_complete_simple_builds_message(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should build correct message format for simple completion."""
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            await llm_client.complete_simple(
                model="test-model",
                prompt="What is Python?",
            )

            call_kwargs = mock_fn.call_args[1]
            assert call_kwargs["messages"] == [{"role": "user", "content": "What is Python?"}]


class TestLLMError:
    """Test LLMError exception."""

    def test_error_message(self) -> None:
        """Should store error message."""
        error = LLMError("Test error message")
        assert str(error) == "Test error message"

    def test_is_exception(self) -> None:
        """Should be an Exception subclass."""
        error = LLMError("Test")
        assert isinstance(error, Exception)
