"""Unit tests for orchestrator module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.orchestrator import (
    _build_persona_config,
    _get_tts_provider,
    _get_voice_id,
    get_active_channels,
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
