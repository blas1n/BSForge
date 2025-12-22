"""Tests for SubtitleGenerator."""

from pathlib import Path

import pytest

from app.config.video import CompositionConfig, SubtitleConfig
from app.services.generator.subtitle import SubtitleFile, SubtitleGenerator
from app.services.generator.templates import ASSTemplateLoader
from app.services.generator.tts.base import WordTimestamp


class TestSubtitleGenerator:
    """Test suite for SubtitleGenerator."""

    @pytest.fixture
    def generator(
        self, subtitle_config: SubtitleConfig, composition_config: CompositionConfig
    ) -> SubtitleGenerator:
        """Create a SubtitleGenerator instance."""
        return SubtitleGenerator(
            config=subtitle_config,
            composition_config=composition_config,
            template_loader=ASSTemplateLoader(),
        )

    def test_generate_from_timestamps(self, generator: SubtitleGenerator) -> None:
        """Test generating subtitles from word timestamps."""
        timestamps = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
            WordTimestamp(word="this", start=1.0, end=1.3),
            WordTimestamp(word="is", start=1.3, end=1.5),
            WordTimestamp(word="a", start=1.5, end=1.6),
            WordTimestamp(word="test", start=1.6, end=2.0),
        ]

        result = generator.generate_from_timestamps(timestamps)

        assert isinstance(result, SubtitleFile)
        assert len(result.segments) > 0

    def test_generate_from_timestamps_empty(self, generator: SubtitleGenerator) -> None:
        """Test generating subtitles from empty timestamps."""
        result = generator.generate_from_timestamps([])

        assert isinstance(result, SubtitleFile)
        assert len(result.segments) == 0

    def test_generate_from_script(self, generator: SubtitleGenerator) -> None:
        """Test generating subtitles from script text."""
        script = "This is the first sentence. This is the second sentence."
        duration = 5.0

        result = generator.generate_from_script(script, duration)

        assert isinstance(result, SubtitleFile)
        assert len(result.segments) > 0

    def test_generate_from_script_empty(self, generator: SubtitleGenerator) -> None:
        """Test generating subtitles from empty script."""
        result = generator.generate_from_script("", 5.0)

        assert isinstance(result, SubtitleFile)
        assert len(result.segments) == 0

    def test_to_srt(self, generator: SubtitleGenerator, tmp_path: Path) -> None:
        """Test SRT file generation."""
        timestamps = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]

        subtitle_file = generator.generate_from_timestamps(timestamps)
        output_path = tmp_path / "subtitle"

        result_path = generator.to_srt(subtitle_file, output_path)

        assert result_path.exists()
        assert result_path.suffix == ".srt"

        content = result_path.read_text()
        assert "1" in content  # Sequence number
        assert "-->" in content  # Timing separator

    def test_to_ass(self, generator: SubtitleGenerator, tmp_path: Path) -> None:
        """Test ASS file generation."""
        timestamps = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]

        subtitle_file = generator.generate_from_timestamps(timestamps)
        output_path = tmp_path / "subtitle"

        result_path = generator.to_ass(subtitle_file, output_path)

        assert result_path.exists()
        assert result_path.suffix == ".ass"

        content = result_path.read_text()
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content


class TestSubtitleSegmentation:
    """Test subtitle text segmentation logic."""

    @pytest.fixture
    def generator(
        self, subtitle_config: SubtitleConfig, composition_config: CompositionConfig
    ) -> SubtitleGenerator:
        """Create a SubtitleGenerator with default config."""
        return SubtitleGenerator(
            config=subtitle_config,
            composition_config=composition_config,
            template_loader=ASSTemplateLoader(),
        )

    def test_split_long_text(self, generator: SubtitleGenerator) -> None:
        """Test splitting long text into segments."""
        long_text = "This is a very long sentence that should be split " * 3

        # Access private method for testing
        segments = generator._split_long_text(long_text)

        assert len(segments) > 1
        # Each segment should be reasonably sized
        for segment in segments:
            assert len(segment) <= 100  # Reasonable max length

    def test_short_text_not_split(self, generator: SubtitleGenerator) -> None:
        """Test that short text is not split."""
        short_text = "Short text"

        segments = generator._split_long_text(short_text)

        assert len(segments) == 1
        assert segments[0] == short_text
