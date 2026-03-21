"""Unit tests for orchestrator module."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.orchestrator import (
    _build_persona_config,
    _get_tts_provider,
    _get_voice_id,
    get_active_channels,
    process_channel,
    run_once,
)


class TestBuildPersonaConfig:
    """Tests for _build_persona_config."""

    def test_returns_none_without_persona(self) -> None:
        """Test returns None when channel has no persona."""
        channel = MagicMock()
        channel.persona = None

        result = _build_persona_config(channel)
        assert result is None

    def test_builds_config_from_persona(self) -> None:
        """Test builds PersonaConfig from channel persona."""
        channel = MagicMock()
        channel.persona.name = "테크브로"
        channel.persona.tagline = "핵심만"
        channel.persona.voice_gender = "male"
        channel.persona.tts_service = "edge-tts"
        channel.persona.voice_id = "ko-KR-InJoonNeural"
        channel.persona.communication_style = {"tone": "friendly", "formality": "semi-formal"}
        channel.persona.perspective = {"core_values": ["기술"], "contrarian_views": []}

        result = _build_persona_config(channel)
        assert result is not None
        assert result.name == "테크브로"
        assert result.tagline == "핵심만"

    def test_returns_none_on_validation_error(self) -> None:
        """Test returns None when persona data causes ValueError."""
        channel = MagicMock()
        channel.name = "test"
        channel.persona.name = None  # Invalid — name is required
        channel.persona.tagline = None
        channel.persona.voice_gender = "invalid_gender"
        channel.persona.tts_service = None
        channel.persona.voice_id = None
        channel.persona.communication_style = None
        channel.persona.perspective = None

        # Should not raise for ValueError/TypeError/KeyError, returns None
        result = _build_persona_config(channel)
        # Either returns config with defaults or None on failure
        assert result is None or result.name is None

    def test_propagates_unexpected_errors(self) -> None:
        """Test that unexpected errors (not ValueError/TypeError/KeyError) propagate."""
        channel = MagicMock()
        channel.name = "test"
        # Accessing .persona raises an unexpected error
        type(channel).persona = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("DB crash"))
        )

        with pytest.raises(RuntimeError, match="DB crash"):
            _build_persona_config(channel)


class TestGetVoiceId:
    """Tests for _get_voice_id."""

    def test_returns_voice_id(self) -> None:
        """Test returns voice ID from persona."""
        channel = MagicMock()
        channel.persona.voice_id = "ko-KR-InJoonNeural"

        assert _get_voice_id(channel) == "ko-KR-InJoonNeural"

    def test_returns_none_without_persona(self) -> None:
        """Test returns None when no persona."""
        channel = MagicMock()
        channel.persona = None

        assert _get_voice_id(channel) is None

    def test_returns_none_without_voice_id(self) -> None:
        """Test returns None when persona has no voice_id."""
        channel = MagicMock()
        channel.persona.voice_id = None

        assert _get_voice_id(channel) is None


class TestGetTTSProvider:
    """Tests for _get_tts_provider."""

    def test_returns_provider(self) -> None:
        """Test returns TTS service from persona."""
        channel = MagicMock()
        channel.persona.tts_service = "elevenlabs"

        assert _get_tts_provider(channel) == "elevenlabs"

    def test_returns_none_without_persona(self) -> None:
        """Test returns None when no persona."""
        channel = MagicMock()
        channel.persona = None

        assert _get_tts_provider(channel) is None


class TestGetActiveChannels:
    """Tests for get_active_channels."""

    @pytest.mark.asyncio
    async def test_returns_active_channels(self) -> None:
        """Test returns active channels from DB."""
        mock_channel = MagicMock()
        mock_channel.name = "Test Channel"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_channel]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        channels = await get_active_channels(mock_session)

        assert len(channels) == 1
        assert channels[0].name == "Test Channel"

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        """Test returns empty list when no active channels."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        channels = await get_active_channels(mock_session)

        assert channels == []


class TestProcessChannel:
    """Tests for process_channel."""

    def _make_channel(self) -> MagicMock:
        """Create a mock channel."""
        channel = MagicMock()
        channel.id = uuid.uuid4()
        channel.name = "Test Channel"
        channel.persona = None
        channel.topic_config = {"sources": [{"type": "hn_rss"}]}
        channel.content_config = {"filtering": {}}
        return channel

    @pytest.mark.asyncio
    @patch("app.orchestrator.create_video_pipeline")
    @patch("app.orchestrator.create_script_generator")
    @patch("app.orchestrator._collect_topics")
    @patch("app.orchestrator.create_prompt_manager")
    @patch("app.orchestrator.create_llm_client")
    @patch("app.orchestrator.create_http_client")
    async def test_happy_path(
        self,
        mock_http: MagicMock,
        mock_llm: MagicMock,
        mock_pm: MagicMock,
        mock_collect: AsyncMock,
        mock_script_gen: MagicMock,
        mock_video_pipe: MagicMock,
    ) -> None:
        """Test full pipeline: collect → script → video."""
        channel = self._make_channel()

        # Mock topic
        topic = MagicMock()
        topic.id = uuid.uuid4()
        topic.title_normalized = "Test Topic"
        topic.summary = "Summary"
        topic.terms = ["test"]
        mock_collect.return_value = [topic]

        # Mock script generator
        script_result = MagicMock()
        script_result.raw_response = '{"scenes": []}'
        script_result.model = "test-model"
        script_result.scene_script.headline = "Test"
        script_result.scene_script.scenes = []
        script_result.scene_script.total_estimated_duration = 30
        mock_script_gen.return_value.generate = AsyncMock(return_value=script_result)

        # Mock video pipeline
        video_result = MagicMock()
        video_result.duration_seconds = 30
        video_result.video_path = "/tmp/test.mp4"
        mock_video_pipe.return_value.generate = AsyncMock(return_value=video_result)

        # Mock DB session for script save
        with patch("app.orchestrator.async_session_maker") as mock_session_maker:
            _mock_async_session_maker(mock_session_maker)
            count = await process_channel(channel)

        assert count == 1

    @pytest.mark.asyncio
    @patch("app.orchestrator._collect_topics")
    @patch("app.orchestrator.create_prompt_manager")
    @patch("app.orchestrator.create_llm_client")
    @patch("app.orchestrator.create_http_client")
    async def test_no_topics_returns_zero(
        self,
        mock_http: MagicMock,
        mock_llm: MagicMock,
        mock_pm: MagicMock,
        mock_collect: AsyncMock,
    ) -> None:
        """Test returns 0 when no topics collected."""
        channel = self._make_channel()
        mock_collect.return_value = []

        count = await process_channel(channel)

        assert count == 0

    @pytest.mark.asyncio
    @patch("app.orchestrator._process_topic")
    @patch("app.orchestrator._collect_topics")
    @patch("app.orchestrator.create_video_pipeline")
    @patch("app.orchestrator.create_script_generator")
    @patch("app.orchestrator.create_prompt_manager")
    @patch("app.orchestrator.create_llm_client")
    @patch("app.orchestrator.create_http_client")
    async def test_topic_error_continues(
        self,
        mock_http: MagicMock,
        mock_llm: MagicMock,
        mock_pm: MagicMock,
        mock_script_gen: MagicMock,
        mock_video_pipe: MagicMock,
        mock_collect: AsyncMock,
        mock_process: AsyncMock,
    ) -> None:
        """Test that one topic failure doesn't stop other topics."""
        channel = self._make_channel()

        topic1 = MagicMock()
        topic1.title_normalized = "Topic 1"
        topic2 = MagicMock()
        topic2.title_normalized = "Topic 2"
        mock_collect.return_value = [topic1, topic2]

        # First topic fails, second succeeds
        mock_process.side_effect = [RuntimeError("boom"), True]

        count = await process_channel(channel)

        assert count == 1
        assert mock_process.call_count == 2


def _mock_async_session_maker(mock_session_maker: MagicMock) -> AsyncMock:
    """Configure async_session_maker mock and return the mock session."""
    mock_session = AsyncMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_session


class TestRunOnce:
    """Tests for run_once."""

    @pytest.mark.asyncio
    @patch("app.orchestrator.get_active_channels")
    @patch("app.orchestrator.async_session_maker")
    async def test_no_active_channels(
        self,
        mock_session_maker: MagicMock,
        mock_get_channels: AsyncMock,
    ) -> None:
        """Test early return when no active channels."""
        _mock_async_session_maker(mock_session_maker)
        mock_get_channels.return_value = []

        await run_once()

        mock_get_channels.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.orchestrator.process_channel")
    @patch("app.orchestrator.get_active_channels")
    @patch("app.orchestrator.async_session_maker")
    async def test_channel_timeout(
        self,
        mock_session_maker: MagicMock,
        mock_get_channels: AsyncMock,
        mock_process: AsyncMock,
    ) -> None:
        """Test timeout handling for slow channels."""
        _mock_async_session_maker(mock_session_maker)

        channel = MagicMock()
        channel.name = "Slow Channel"
        mock_get_channels.return_value = [channel]

        # Simulate timeout
        mock_process.side_effect = TimeoutError()

        # Should not raise
        await run_once()
