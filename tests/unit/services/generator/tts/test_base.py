"""Unit tests for TTS base module."""

from pathlib import Path

import pytest

from app.services.generator.tts.base import (
    EDGE_TTS_VOICES_EN,
    EDGE_TTS_VOICES_KO,
    SceneTTSResult,
    TTSResult,
    TTSSynthesisConfig,
    VoiceInfo,
    WordTimestamp,
)


class TestWordTimestamp:
    """Tests for WordTimestamp dataclass."""

    def test_valid_timestamp(self):
        """Test creating a valid word timestamp."""
        wt = WordTimestamp(word="hello", start=0.5, end=1.0)

        assert wt.word == "hello"
        assert wt.start == 0.5
        assert wt.end == 1.0

    def test_zero_start_time(self):
        """Test timestamp with zero start time."""
        wt = WordTimestamp(word="start", start=0.0, end=0.5)

        assert wt.start == 0.0

    def test_same_start_end_time(self):
        """Test timestamp where start equals end."""
        wt = WordTimestamp(word="instant", start=1.0, end=1.0)

        assert wt.start == wt.end

    def test_negative_start_raises(self):
        """Test that negative start time raises ValueError."""
        with pytest.raises(ValueError, match="Start time cannot be negative"):
            WordTimestamp(word="test", start=-0.1, end=1.0)

    def test_end_before_start_raises(self):
        """Test that end before start raises ValueError."""
        with pytest.raises(ValueError, match="End time cannot be before start time"):
            WordTimestamp(word="test", start=1.0, end=0.5)


class TestTTSResult:
    """Tests for TTSResult dataclass."""

    def test_default_values(self):
        """Test TTSResult default values."""
        result = TTSResult(
            audio_path=Path("/tmp/test.mp3"),
            duration_seconds=5.0,
        )

        assert result.audio_path == Path("/tmp/test.mp3")
        assert result.duration_seconds == 5.0
        assert result.word_timestamps is None
        assert result.sample_rate == 24000
        assert result.format == "mp3"

    def test_with_word_timestamps(self):
        """Test TTSResult with word timestamps."""
        timestamps = [
            WordTimestamp(word="hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]
        result = TTSResult(
            audio_path=Path("/tmp/test.mp3"),
            duration_seconds=1.0,
            word_timestamps=timestamps,
        )

        assert result.word_timestamps is not None
        assert len(result.word_timestamps) == 2

    def test_custom_format(self):
        """Test TTSResult with custom format."""
        result = TTSResult(
            audio_path=Path("/tmp/test.wav"),
            duration_seconds=5.0,
            sample_rate=44100,
            format="wav",
        )

        assert result.format == "wav"
        assert result.sample_rate == 44100


class TestSceneTTSResult:
    """Tests for SceneTTSResult dataclass."""

    def test_default_values(self):
        """Test SceneTTSResult default values."""
        result = SceneTTSResult(
            scene_index=0,
            scene_type="hook",
            audio_path=Path("/tmp/scene_000.mp3"),
            duration_seconds=3.0,
        )

        assert result.scene_index == 0
        assert result.scene_type == "hook"
        assert result.duration_seconds == 3.0
        assert result.word_timestamps is None
        assert result.start_offset == 0.0

    def test_with_start_offset(self):
        """Test SceneTTSResult with start offset."""
        result = SceneTTSResult(
            scene_index=2,
            scene_type="content",
            audio_path=Path("/tmp/scene_002.mp3"),
            duration_seconds=5.0,
            start_offset=8.0,
        )

        assert result.start_offset == 8.0


class TestTTSSynthesisConfig:
    """Tests for TTSSynthesisConfig dataclass."""

    def test_default_values(self):
        """Test TTSSynthesisConfig default values."""
        config = TTSSynthesisConfig(voice_id="ko-KR-InJoonNeural")

        assert config.voice_id == "ko-KR-InJoonNeural"
        assert config.speed == 1.0
        assert config.pitch == 0
        assert config.volume == 0
        assert config.output_format == "mp3"

    def test_valid_speed_range(self):
        """Test valid speed values."""
        config_slow = TTSSynthesisConfig(voice_id="test", speed=0.5)
        config_fast = TTSSynthesisConfig(voice_id="test", speed=2.0)

        assert config_slow.speed == 0.5
        assert config_fast.speed == 2.0

    def test_invalid_speed_too_slow(self):
        """Test that speed below 0.5 raises ValueError."""
        with pytest.raises(ValueError, match="Speed must be between"):
            TTSSynthesisConfig(voice_id="test", speed=0.4)

    def test_invalid_speed_too_fast(self):
        """Test that speed above 2.0 raises ValueError."""
        with pytest.raises(ValueError, match="Speed must be between"):
            TTSSynthesisConfig(voice_id="test", speed=2.1)

    def test_valid_pitch_range(self):
        """Test valid pitch values."""
        config_low = TTSSynthesisConfig(voice_id="test", pitch=-50)
        config_high = TTSSynthesisConfig(voice_id="test", pitch=50)

        assert config_low.pitch == -50
        assert config_high.pitch == 50

    def test_invalid_pitch_too_low(self):
        """Test that pitch below -50 raises ValueError."""
        with pytest.raises(ValueError, match="Pitch must be between"):
            TTSSynthesisConfig(voice_id="test", pitch=-51)

    def test_invalid_pitch_too_high(self):
        """Test that pitch above 50 raises ValueError."""
        with pytest.raises(ValueError, match="Pitch must be between"):
            TTSSynthesisConfig(voice_id="test", pitch=51)

    def test_valid_volume_range(self):
        """Test valid volume values."""
        config_quiet = TTSSynthesisConfig(voice_id="test", volume=-50)
        config_loud = TTSSynthesisConfig(voice_id="test", volume=50)

        assert config_quiet.volume == -50
        assert config_loud.volume == 50

    def test_invalid_volume(self):
        """Test that volume outside range raises ValueError."""
        with pytest.raises(ValueError, match="Volume must be between"):
            TTSSynthesisConfig(voice_id="test", volume=51)


class TestVoiceInfo:
    """Tests for VoiceInfo dataclass."""

    def test_required_fields(self):
        """Test VoiceInfo with required fields."""
        voice = VoiceInfo(
            voice_id="ko-KR-InJoonNeural",
            name="인준",
            language="ko-KR",
            gender="male",
        )

        assert voice.voice_id == "ko-KR-InJoonNeural"
        assert voice.name == "인준"
        assert voice.language == "ko-KR"
        assert voice.gender == "male"

    def test_default_values(self):
        """Test VoiceInfo default values."""
        voice = VoiceInfo(
            voice_id="test",
            name="Test",
            language="en-US",
            gender="neutral",
        )

        assert voice.description is None
        assert voice.is_neural is True
        assert voice.sample_url is None

    def test_all_gender_values(self):
        """Test all valid gender values."""
        for gender in ["male", "female", "neutral"]:
            voice = VoiceInfo(
                voice_id="test",
                name="Test",
                language="en-US",
                gender=gender,
            )
            assert voice.gender == gender


class TestEdgeTTSVoiceConstants:
    """Tests for Edge TTS voice constants."""

    def test_korean_voices_exist(self):
        """Test that Korean voice constants exist."""
        assert len(EDGE_TTS_VOICES_KO) > 0

    def test_korean_male_voices(self):
        """Test Korean male voices."""
        male_voices = [v for v in EDGE_TTS_VOICES_KO.values() if v.gender == "male"]
        assert len(male_voices) >= 1

        # Check InJoon voice exists
        assert "ko-KR-InJoonNeural" in EDGE_TTS_VOICES_KO
        assert EDGE_TTS_VOICES_KO["ko-KR-InJoonNeural"].language == "ko-KR"

    def test_korean_female_voices(self):
        """Test Korean female voices."""
        female_voices = [v for v in EDGE_TTS_VOICES_KO.values() if v.gender == "female"]
        assert len(female_voices) >= 1

        # Check SunHi voice exists
        assert "ko-KR-SunHiNeural" in EDGE_TTS_VOICES_KO

    def test_english_voices_exist(self):
        """Test that English voice constants exist."""
        assert len(EDGE_TTS_VOICES_EN) > 0

    def test_english_voices_have_correct_language(self):
        """Test English voices have correct language code."""
        for voice in EDGE_TTS_VOICES_EN.values():
            assert voice.language.startswith("en-")

    def test_all_voices_are_neural(self):
        """Test that all voice constants are neural voices."""
        all_voices = list(EDGE_TTS_VOICES_KO.values()) + list(EDGE_TTS_VOICES_EN.values())
        for voice in all_voices:
            assert voice.is_neural is True

    def test_voice_ids_match_keys(self):
        """Test that voice_id matches dictionary keys."""
        for voice_id, voice in EDGE_TTS_VOICES_KO.items():
            assert voice.voice_id == voice_id

        for voice_id, voice in EDGE_TTS_VOICES_EN.items():
            assert voice.voice_id == voice_id
