"""Unit tests for TTS utility functions."""

from pathlib import Path

from app.services.generator.tts.base import SceneTTSResult, WordTimestamp
from app.services.generator.tts.utils import adjust_scene_offsets


class TestAdjustSceneOffsets:
    """Tests for adjust_scene_offsets function."""

    def test_single_scene(self):
        """Test adjusting offset for single scene."""
        results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="hook",
                audio_path=Path("/tmp/scene_000.mp3"),
                duration_seconds=3.0,
            )
        ]

        adjust_scene_offsets(results)

        assert results[0].start_offset == 0.0

    def test_multiple_scenes(self):
        """Test adjusting offsets for multiple scenes."""
        results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="hook",
                audio_path=Path("/tmp/scene_000.mp3"),
                duration_seconds=3.0,
            ),
            SceneTTSResult(
                scene_index=1,
                scene_type="content",
                audio_path=Path("/tmp/scene_001.mp3"),
                duration_seconds=5.0,
            ),
            SceneTTSResult(
                scene_index=2,
                scene_type="conclusion",
                audio_path=Path("/tmp/scene_002.mp3"),
                duration_seconds=2.0,
            ),
        ]

        adjust_scene_offsets(results)

        assert results[0].start_offset == 0.0
        assert results[1].start_offset == 3.0
        assert results[2].start_offset == 8.0

    def test_with_gap_duration(self):
        """Test adjusting offsets with gap between scenes."""
        results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="hook",
                audio_path=Path("/tmp/scene_000.mp3"),
                duration_seconds=3.0,
            ),
            SceneTTSResult(
                scene_index=1,
                scene_type="content",
                audio_path=Path("/tmp/scene_001.mp3"),
                duration_seconds=5.0,
            ),
        ]

        adjust_scene_offsets(results, gap_duration=0.5)

        assert results[0].start_offset == 0.0
        # 3.0 (duration) + 0.5 (gap) = 3.5
        assert results[1].start_offset == 3.5

    def test_empty_list(self):
        """Test with empty list."""
        results: list[SceneTTSResult] = []

        adjust_scene_offsets(results)

        assert len(results) == 0

    def test_overwrites_existing_offsets(self):
        """Test that existing offsets are overwritten."""
        results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="hook",
                audio_path=Path("/tmp/scene_000.mp3"),
                duration_seconds=3.0,
                start_offset=100.0,  # Wrong offset
            ),
            SceneTTSResult(
                scene_index=1,
                scene_type="content",
                audio_path=Path("/tmp/scene_001.mp3"),
                duration_seconds=5.0,
                start_offset=200.0,  # Wrong offset
            ),
        ]

        adjust_scene_offsets(results)

        assert results[0].start_offset == 0.0
        assert results[1].start_offset == 3.0

    def test_modifies_in_place(self):
        """Test that function modifies list in place."""
        result = SceneTTSResult(
            scene_index=0,
            scene_type="hook",
            audio_path=Path("/tmp/scene_000.mp3"),
            duration_seconds=3.0,
            start_offset=100.0,
        )
        results = [result]

        adjust_scene_offsets(results)

        # Same object should be modified
        assert result.start_offset == 0.0
        assert results[0] is result


class TestWordTimestampUsage:
    """Tests for WordTimestamp usage in scene results."""

    def test_scene_result_with_timestamps(self):
        """Test SceneTTSResult with word timestamps."""
        timestamps = [
            WordTimestamp(word="hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]
        result = SceneTTSResult(
            scene_index=0,
            scene_type="content",
            audio_path=Path("/tmp/test.mp3"),
            duration_seconds=1.0,
            word_timestamps=timestamps,
        )

        assert result.word_timestamps is not None
        assert len(result.word_timestamps) == 2
        assert result.word_timestamps[0].word == "hello"
        assert result.word_timestamps[1].word == "world"

    def test_adjust_offsets_preserves_timestamps(self):
        """Test that adjust_scene_offsets preserves word timestamps."""
        timestamps = [
            WordTimestamp(word="test", start=0.0, end=0.5),
        ]
        results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="hook",
                audio_path=Path("/tmp/scene_000.mp3"),
                duration_seconds=3.0,
                word_timestamps=timestamps,
            ),
        ]

        adjust_scene_offsets(results)

        assert results[0].word_timestamps is not None
        assert len(results[0].word_timestamps) == 1
        assert results[0].word_timestamps[0].word == "test"
