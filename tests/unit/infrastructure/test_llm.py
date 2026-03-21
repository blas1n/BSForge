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
        config = LLMConfig(model="test-model")

        assert config.model == "test-model"
        assert config.max_tokens == 1000
        assert config.temperature == 0.7
        assert config.timeout == 60

    def test_custom_values(self) -> None:
        """Should accept custom values."""
        config = LLMConfig(
            model="custom-model",
            max_tokens=2000,
            temperature=0.5,
            timeout=120,
        )

        assert config.model == "custom-model"
        assert config.max_tokens == 2000
        assert config.temperature == 0.5
        assert config.timeout == 120

    def test_rejects_non_positive_timeout(self) -> None:
        """Should reject zero or negative timeout."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            LLMConfig(model="test-model", timeout=0)

        with pytest.raises(ValueError, match="timeout must be positive"):
            LLMConfig(model="test-model", timeout=-5)

    def test_from_prompt_settings(self) -> None:
        """Should create config from LLMSettings."""
        mock_settings = MagicMock()
        mock_settings.model = "override-model"
        mock_settings.max_tokens = 1500
        mock_settings.temperature = 0.8

        config = LLMConfig.from_prompt_settings(mock_settings, timeout=90)

        assert config.model == "override-model"
        assert config.max_tokens == 1500
        assert config.temperature == 0.8
        assert config.timeout == 90

    def test_from_prompt_settings_default_timeout(self) -> None:
        """Should use default timeout when not specified."""
        mock_settings = MagicMock()
        mock_settings.model = ""
        mock_settings.max_tokens = 500
        mock_settings.temperature = 0.3

        config = LLMConfig.from_prompt_settings(mock_settings)

        assert config.timeout == 60

    def test_from_prompt_settings_empty_model(self) -> None:
        """Should allow empty model from prompt settings."""
        mock_settings = MagicMock()
        mock_settings.model = ""
        mock_settings.max_tokens = 500
        mock_settings.temperature = 0.3

        config = LLMConfig.from_prompt_settings(mock_settings)

        assert config.model == ""


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_basic_response(self) -> None:
        """Should store response data correctly."""
        response = LLMResponse(
            content="Hello, world!",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        assert response.content == "Hello, world!"
        assert response.model == "test-model"
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
        mock_response.model = "test-model"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30

        return mock_response

    @pytest.fixture
    def llm_client(self) -> LLMClient:
        """Create LLMClient instance."""
        return LLMClient(
            base_url="http://localhost:11434",
            api_key="test-key",
            default_model="test-model",
        )

    def test_init(self) -> None:
        """Should initialize with gateway settings."""
        client = LLMClient(
            base_url="http://localhost:11434",
            api_key="test-key",
            default_model="test-model",
        )
        assert client.base_url == "http://localhost:11434"
        assert client.api_key == "test-key"
        assert client.default_model == "test-model"

    def test_init_defaults(self) -> None:
        """Should initialize with empty defaults."""
        client = LLMClient()
        assert client.base_url == ""
        assert client.api_key == ""
        assert client.default_model == ""

    @pytest.mark.asyncio
    async def test_complete_basic(self, llm_client: LLMClient, mock_acompletion: MagicMock) -> None:
        """Should complete request and return response."""
        with patch(
            "app.infrastructure.llm.acompletion",
            new_callable=AsyncMock,
            return_value=mock_acompletion,
        ):
            config = LLMConfig(model="test-model")
            messages = [{"role": "user", "content": "Hello"}]

            response = await llm_client.complete(config, messages)

            assert response.content == "Generated response"
            assert response.model == "test-model"
            assert response.usage["prompt_tokens"] == 10
            assert response.usage["completion_tokens"] == 20
            assert response.usage["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_complete_passes_config(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should pass config parameters and gateway settings to acompletion."""
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            config = LLMConfig(
                model="custom-model",
                max_tokens=2000,
                temperature=0.5,
                timeout=120,
            )
            messages = [{"role": "user", "content": "Test"}]

            await llm_client.complete(config, messages)

            mock_fn.assert_called_once_with(
                model="openai/custom-model",
                messages=messages,
                max_tokens=2000,
                temperature=0.5,
                timeout=120,
                api_base="http://localhost:11434",
                api_key="test-key",
            )

    @pytest.mark.asyncio
    async def test_complete_falls_back_to_default_model(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should use default_model when config.model is empty."""
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            config = LLMConfig(model="", max_tokens=500, temperature=0.3)
            messages = [{"role": "user", "content": "Test"}]

            await llm_client.complete(config, messages)

            call_kwargs = mock_fn.call_args[1]
            assert call_kwargs["model"] == "openai/test-model"

    @pytest.mark.asyncio
    async def test_complete_with_kwargs(
        self, llm_client: LLMClient, mock_acompletion: MagicMock
    ) -> None:
        """Should pass additional kwargs to acompletion."""
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            config = LLMConfig(model="test-model")
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
            config = LLMConfig(model="test-model")
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
            config = LLMConfig(model="test-model")
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
            config = LLMConfig(model="test-model")

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
                model="test-model",
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

    @pytest.mark.asyncio
    async def test_complete_empty_base_url_passes_none(self, mock_acompletion: MagicMock) -> None:
        """Should pass None for api_base when base_url is empty."""
        client = LLMClient(base_url="", api_key="", default_model="test-model")
        mock_fn = AsyncMock(return_value=mock_acompletion)

        with patch("app.infrastructure.llm.acompletion", mock_fn):
            config = LLMConfig(model="test-model")
            await client.complete(config, [{"role": "user", "content": "Hi"}])

            call_kwargs = mock_fn.call_args[1]
            assert call_kwargs["api_base"] is None
            assert call_kwargs["api_key"] is None


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
