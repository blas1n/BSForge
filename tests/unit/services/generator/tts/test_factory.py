"""Unit tests for TTS engine factory."""

from unittest.mock import MagicMock

import pytest

from app.config.video import TTSProviderConfig
from app.services.generator.tts.base import BaseTTSEngine
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.tts.elevenlabs import ElevenLabsEngine
from app.services.generator.tts.factory import TTSEngineFactory


@pytest.fixture
def mock_ffmpeg():
    """Create mock FFmpeg wrapper."""
    return MagicMock()


@pytest.fixture
def tts_config():
    """Create TTS provider config."""
    return TTSProviderConfig(
        provider="edge-tts",
        default_voice_ko_male="ko-KR-InJoonNeural",
        default_voice_ko_female="ko-KR-SunHiNeural",
        default_voice_en="en-US-AriaNeural",
    )


@pytest.fixture
def factory(mock_ffmpeg, tts_config):
    """Create TTS engine factory."""
    return TTSEngineFactory(
        ffmpeg_wrapper=mock_ffmpeg,
        config=tts_config,
        elevenlabs_api_key="test-api-key",
    )


class TestTTSEngineFactory:
    """Tests for TTSEngineFactory."""

    def test_init(self, factory, tts_config):
        """Test factory initialization."""
        assert factory._config == tts_config
        assert factory._elevenlabs_api_key == "test-api-key"
        assert len(factory._engines) == 0

    def test_available_providers(self, factory):
        """Test available_providers property."""
        providers = factory.available_providers

        assert "edge-tts" in providers
        assert "elevenlabs" in providers

    def test_get_engine_edge_tts(self, factory):
        """Test getting Edge TTS engine."""
        engine = factory.get_engine("edge-tts")

        assert isinstance(engine, EdgeTTSEngine)
        assert isinstance(engine, BaseTTSEngine)

    def test_get_engine_elevenlabs(self, factory):
        """Test getting ElevenLabs engine."""
        engine = factory.get_engine("elevenlabs")

        assert isinstance(engine, ElevenLabsEngine)
        assert isinstance(engine, BaseTTSEngine)

    def test_get_engine_default_provider(self, factory):
        """Test getting engine with default provider from config."""
        engine = factory.get_engine(None)

        # Config default is edge-tts
        assert isinstance(engine, EdgeTTSEngine)

    def test_get_engine_caches_instance(self, factory):
        """Test that factory caches engine instances."""
        engine1 = factory.get_engine("edge-tts")
        engine2 = factory.get_engine("edge-tts")

        assert engine1 is engine2

    def test_get_engine_different_providers_different_instances(self, factory):
        """Test that different providers return different instances."""
        edge_engine = factory.get_engine("edge-tts")
        elevenlabs_engine = factory.get_engine("elevenlabs")

        assert edge_engine is not elevenlabs_engine

    def test_get_engine_unsupported_raises(self, factory):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported TTS provider"):
            factory.get_engine("unsupported-provider")


class TestTTSEngineFactoryVoiceDefaults:
    """Tests for TTSEngineFactory voice default methods."""

    def test_get_default_voice_id_korean_male(self, factory):
        """Test getting default Korean male voice."""
        voice_id = factory.get_default_voice_id(language="ko", gender="male")

        assert voice_id == "ko-KR-InJoonNeural"

    def test_get_default_voice_id_korean_female(self, factory):
        """Test getting default Korean female voice."""
        voice_id = factory.get_default_voice_id(language="ko", gender="female")

        assert voice_id == "ko-KR-SunHiNeural"

    def test_get_default_voice_id_korean_kr(self, factory):
        """Test getting default voice with ko-KR language code."""
        voice_id = factory.get_default_voice_id(language="ko-KR", gender="male")

        assert voice_id == "ko-KR-InJoonNeural"

    def test_get_default_voice_id_english(self, factory):
        """Test getting default English voice."""
        voice_id = factory.get_default_voice_id(language="en", gender="male")

        assert voice_id == "en-US-AriaNeural"

    def test_get_default_voice_id_english_us(self, factory):
        """Test getting default voice with en-US language code."""
        voice_id = factory.get_default_voice_id(language="en-US", gender="female")

        assert voice_id == "en-US-AriaNeural"

    def test_get_default_voice_id_other_language(self, factory):
        """Test getting default voice for other languages defaults to English."""
        voice_id = factory.get_default_voice_id(language="ja", gender="male")

        assert voice_id == "en-US-AriaNeural"


class TestTTSEngineFactoryWithDifferentConfigs:
    """Tests for TTSEngineFactory with different configurations."""

    def test_factory_with_elevenlabs_default(self, mock_ffmpeg):
        """Test factory with ElevenLabs as default provider."""
        config = TTSProviderConfig(
            provider="elevenlabs",
            default_voice_ko_male="ko-KR-InJoonNeural",
            default_voice_ko_female="ko-KR-SunHiNeural",
            default_voice_en="en-US-AriaNeural",
        )
        factory = TTSEngineFactory(
            ffmpeg_wrapper=mock_ffmpeg,
            config=config,
            elevenlabs_api_key="test-key",
        )

        engine = factory.get_engine(None)

        assert isinstance(engine, ElevenLabsEngine)

    def test_factory_with_custom_default_voices(self, mock_ffmpeg):
        """Test factory with custom default voices."""
        config = TTSProviderConfig(
            provider="edge-tts",
            default_voice_ko_male="ko-KR-BongJinNeural",
            default_voice_ko_female="ko-KR-JiMinNeural",
            default_voice_en="en-US-GuyNeural",
        )
        factory = TTSEngineFactory(
            ffmpeg_wrapper=mock_ffmpeg,
            config=config,
            elevenlabs_api_key="test-key",
        )

        assert factory.get_default_voice_id("ko", "male") == "ko-KR-BongJinNeural"
        assert factory.get_default_voice_id("ko", "female") == "ko-KR-JiMinNeural"
        assert factory.get_default_voice_id("en", "male") == "en-US-GuyNeural"
