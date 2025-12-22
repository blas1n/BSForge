"""Tests for TTS engines and factory."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config.video import TTSConfig
from app.services.generator.tts.base import TTSConfig as TTSConfigDataclass
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.tts.factory import TTSEngineFactory


class TestTTSFactory:
    """Test suite for TTSEngineFactory."""

    def test_get_edge_engine(self) -> None:
        """Test getting Edge TTS engine."""
        factory = TTSEngineFactory()
        engine = factory.get_engine("edge-tts")

        assert isinstance(engine, EdgeTTSEngine)

    def test_get_engine_caching(self) -> None:
        """Test that engines are cached."""
        factory = TTSEngineFactory()

        engine1 = factory.get_engine("edge-tts")
        engine2 = factory.get_engine("edge-tts")

        assert engine1 is engine2

    def test_get_default_engine(self) -> None:
        """Test getting default engine from config."""
        config = TTSConfig(provider="edge-tts")
        factory = TTSEngineFactory(config=config)

        engine = factory.get_engine()

        assert isinstance(engine, EdgeTTSEngine)

    def test_get_unknown_engine_raises(self) -> None:
        """Test that unknown engine type raises ValueError."""
        factory = TTSEngineFactory()

        with pytest.raises(ValueError, match="Unsupported TTS provider"):
            factory.get_engine("unknown-engine")

    def test_get_default_voice_id_korean_male(self) -> None:
        """Test getting default Korean male voice."""
        factory = TTSEngineFactory()
        voice_id = factory.get_default_voice_id(language="ko", gender="male")

        assert voice_id is not None
        assert "Korean" in voice_id or "ko-KR" in voice_id

    def test_get_default_voice_id_english(self) -> None:
        """Test getting default English voice."""
        factory = TTSEngineFactory()
        voice_id = factory.get_default_voice_id(language="en")

        assert voice_id is not None


class TestEdgeTTSEngine:
    """Test suite for EdgeTTSEngine."""

    @pytest.fixture
    def engine(self) -> EdgeTTSEngine:
        """Create an EdgeTTSEngine instance."""
        return EdgeTTSEngine()

    def test_engine_initialization(self, engine: EdgeTTSEngine) -> None:
        """Test engine initializes correctly."""
        assert engine is not None

    def test_get_available_voices_korean(self, engine: EdgeTTSEngine) -> None:
        """Test getting available Korean voices."""
        voices = engine.get_available_voices(language="ko")

        assert len(voices) > 0
        for voice in voices:
            # VoiceInfo is a dataclass with voice_id and name attributes
            assert hasattr(voice, "voice_id")
            assert hasattr(voice, "name")

    def test_get_available_voices_english(self, engine: EdgeTTSEngine) -> None:
        """Test getting available English voices."""
        voices = engine.get_available_voices(language="en")

        assert len(voices) > 0

    @pytest.mark.asyncio
    async def test_get_audio_duration(self, engine: EdgeTTSEngine, tmp_path: Path) -> None:
        """Test audio duration calculation with mock FFmpegWrapper."""
        audio_path = tmp_path / "test.mp3"
        audio_path.write_bytes(b"fake audio")

        mock_wrapper = AsyncMock()
        mock_wrapper.get_duration.return_value = 10.5

        with patch(
            "app.services.generator.tts.edge.get_ffmpeg_wrapper",
            return_value=mock_wrapper,
        ):
            duration = await engine.get_audio_duration(audio_path)

            assert duration == 10.5
            mock_wrapper.get_duration.assert_called_once_with(audio_path)


class TestTTSConfig:
    """Test TTS configuration."""

    def test_default_config(self) -> None:
        """Test default TTS configuration."""
        config = TTSConfig()

        assert config.provider == "edge-tts"
        assert config.speed >= 0.5
        assert config.speed <= 2.0
        assert config.pitch >= -50
        assert config.pitch <= 50

    def test_tts_config_dataclass(self) -> None:
        """Test TTSConfig dataclass."""
        # Volume range is -50 to 50 (not 0-100)
        config = TTSConfigDataclass(
            voice_id="test-voice",
            speed=1.2,
            pitch=5,
            volume=10,
        )

        assert config.voice_id == "test-voice"
        assert config.speed == 1.2
        assert config.pitch == 5
        assert config.volume == 10
