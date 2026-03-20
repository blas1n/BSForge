"""Tests for SubtitleGenerator."""

from pathlib import Path

import pytest

from app.config.video import CompositionConfig, SubtitleConfig
from app.models.scene import Scene, SceneType
from app.services.generator.subtitle import SubtitleFile, SubtitleGenerator, SubtitleSegment
from app.services.generator.templates import ASSTemplateLoader
from app.services.generator.tts.base import SceneTTSResult, WordTimestamp


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


class TestGenerateFromSceneResults:
    """Test scene-based subtitle generation with overlap prevention."""

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

    def _make_scene(self, text: str, tts_text: str | None = None) -> Scene:
        """Helper to create a Scene object."""
        return Scene(
            scene_type=SceneType.CONTENT,
            text=text,
            visual_keyword="test keyword",
            tts_text=tts_text,
        )

    def _make_tts_result(
        self,
        index: int,
        duration: float,
        start_offset: float,
        words: list[WordTimestamp] | None = None,
        tmp_path: Path = Path("/tmp"),
    ) -> SceneTTSResult:
        """Helper to create a SceneTTSResult."""
        return SceneTTSResult(
            scene_index=index,
            scene_type="content",
            audio_path=tmp_path / f"scene_{index}.mp3",
            duration_seconds=duration,
            word_timestamps=words,
            start_offset=start_offset,
        )

    def test_no_overlap_between_segments(self, generator: SubtitleGenerator) -> None:
        """Consecutive subtitle segments must not overlap in time."""
        scenes = [
            self._make_scene("여러분 AI가 코딩을 대체한다고요"),
            self._make_scene("근데 솔직히 아직 멀었습니다"),
        ]
        tts_results = [
            self._make_tts_result(
                0,
                3.0,
                0.0,
                words=[
                    WordTimestamp(word="여러분", start=0.0, end=0.5),
                    WordTimestamp(word="AI가", start=0.5, end=1.0),
                    WordTimestamp(word="코딩을", start=1.0, end=1.5),
                    WordTimestamp(word="대체한다고요", start=1.5, end=3.0),
                ],
            ),
            self._make_tts_result(
                1,
                3.0,
                3.0,
                words=[
                    WordTimestamp(word="근데", start=0.0, end=0.5),
                    WordTimestamp(word="솔직히", start=0.5, end=1.0),
                    WordTimestamp(word="아직", start=1.0, end=1.5),
                    WordTimestamp(word="멀었습니다", start=1.5, end=3.0),
                ],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        assert len(result.segments) >= 2

        for i in range(len(result.segments) - 1):
            gap = result.segments[i + 1].start - result.segments[i].end
            assert gap >= 0.05 - 1e-9, (
                f"Segments {i} and {i + 1} overlap: "
                f"seg[{i}].end={result.segments[i].end}, "
                f"seg[{i + 1}].start={result.segments[i + 1].start}"
            )

    def test_segments_have_spaces_in_text(self, generator: SubtitleGenerator) -> None:
        """Segment text must contain spaces between Korean words."""
        scenes = [self._make_scene("여러분 AI가 코딩을 대체한다고요")]
        tts_results = [
            self._make_tts_result(
                0,
                3.0,
                0.0,
                words=[
                    WordTimestamp(word="여러분", start=0.0, end=0.5),
                    WordTimestamp(word="AI가", start=0.5, end=1.0),
                    WordTimestamp(word="코딩을", start=1.0, end=1.5),
                    WordTimestamp(word="대체한다고요", start=1.5, end=3.0),
                ],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        for seg in result.segments:
            # Each multi-word segment should contain spaces
            words_in_text = seg.text.split()
            if len(words_in_text) > 1:
                assert " " in seg.text, f"No spaces in segment text: '{seg.text}'"

    def test_karaoke_words_preserved_when_no_tts_text(self, generator: SubtitleGenerator) -> None:
        """When tts_text is None, word timestamps should be preserved for karaoke."""
        scenes = [self._make_scene("여러분 AI가 대체한다고요", tts_text=None)]
        tts_results = [
            self._make_tts_result(
                0,
                3.0,
                0.0,
                words=[
                    WordTimestamp(word="여러분", start=0.0, end=0.8),
                    WordTimestamp(word="AI가", start=0.8, end=1.5),
                    WordTimestamp(word="대체한다고요", start=1.5, end=3.0),
                ],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        # At least one segment should have karaoke word data
        has_words = any(seg.words is not None for seg in result.segments)
        assert has_words, "Expected karaoke word data when tts_text is None"

    def test_segments_clamped_to_scene_boundary(self, generator: SubtitleGenerator) -> None:
        """Subtitle end times must not exceed their scene's boundary."""
        scenes = [
            self._make_scene("첫 번째 씬 텍스트입니다"),
            self._make_scene("두 번째 씬 텍스트입니다"),
        ]
        # Scene 0: 0.0–3.0s, but last word ends at 3.15s (exceeds boundary)
        tts_results = [
            self._make_tts_result(
                0,
                3.0,
                0.0,
                words=[
                    WordTimestamp(word="첫", start=0.0, end=0.5),
                    WordTimestamp(word="번째", start=0.5, end=1.0),
                    WordTimestamp(word="씬", start=1.0, end=1.5),
                    WordTimestamp(word="텍스트입니다", start=1.5, end=3.15),
                ],
            ),
            self._make_tts_result(
                1,
                3.0,
                3.0,
                words=[
                    WordTimestamp(word="두", start=0.0, end=0.5),
                    WordTimestamp(word="번째", start=0.5, end=1.0),
                    WordTimestamp(word="씬", start=1.0, end=1.5),
                    WordTimestamp(word="텍스트입니다", start=1.5, end=3.0),
                ],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        # All segments from scene 0 must end before 3.0s (the scene boundary)
        scene_0_boundary = 3.0
        for seg in result.segments:
            if seg.start < scene_0_boundary:
                assert (
                    seg.end <= scene_0_boundary
                ), f"Segment overflows scene boundary: end={seg.end} > {scene_0_boundary}"

    def test_empty_scene_results(self, generator: SubtitleGenerator) -> None:
        """Empty input produces empty output."""
        result = generator.generate_from_scene_results(scene_results=[], scenes=[])

        assert len(result.segments) == 0

    def test_tts_text_path_uses_proportional_timing(self, generator: SubtitleGenerator) -> None:
        """When scene has tts_text, proportional timing is used for display text."""
        scenes = [
            self._make_scene(
                text="여러분 AI가 코딩을 대체한다고요",
                tts_text="여러분 에이아이가 코딩을 대체한다고요",
            )
        ]
        tts_results = [
            self._make_tts_result(
                0,
                3.0,
                0.0,
                words=[
                    WordTimestamp(word="여러분", start=0.0, end=0.5),
                    WordTimestamp(word="에이아이가", start=0.5, end=1.2),
                    WordTimestamp(word="코딩을", start=1.2, end=1.8),
                    WordTimestamp(word="대체한다고요", start=1.8, end=3.0),
                ],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        assert len(result.segments) >= 1
        # Display text should use scene.text, not tts_text
        full_text = " ".join(seg.text for seg in result.segments)
        assert "AI가" in full_text
        assert "에이아이가" not in full_text

    def test_manual_subtitle_segments(self, generator: SubtitleGenerator) -> None:
        """When scene has subtitle_segments, they are used directly."""
        scene = self._make_scene(text="첫 번째 문장 두 번째 문장 세 번째 문장")
        scene.subtitle_segments = ["첫 번째 문장", "두 번째 문장", "세 번째 문장"]
        scenes = [scene]
        tts_results = [
            self._make_tts_result(
                0,
                4.0,
                0.0,
                words=[
                    WordTimestamp(word="첫", start=0.0, end=0.3),
                    WordTimestamp(word="번째", start=0.3, end=0.6),
                    WordTimestamp(word="문장", start=0.6, end=1.0),
                    WordTimestamp(word="두", start=1.0, end=1.3),
                    WordTimestamp(word="번째", start=1.3, end=1.8),
                    WordTimestamp(word="문장", start=1.8, end=2.5),
                    WordTimestamp(word="세", start=2.5, end=2.8),
                    WordTimestamp(word="번째", start=2.8, end=3.2),
                    WordTimestamp(word="문장", start=3.2, end=4.0),
                ],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        assert len(result.segments) == 3
        assert "첫 번째 문장" in result.segments[0].text
        assert "두 번째 문장" in result.segments[1].text
        assert "세 번째 문장" in result.segments[2].text

    def test_manual_subtitle_segments_no_timestamps(self, generator: SubtitleGenerator) -> None:
        """Manual segments without word timestamps use proportional timing."""
        scene = self._make_scene(text="첫 번째 두 번째")
        scene.subtitle_segments = ["첫 번째", "두 번째"]
        scenes = [scene]
        tts_results = [self._make_tts_result(0, 4.0, 1.0, words=None)]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        assert len(result.segments) == 2
        # First segment starts at scene offset
        assert result.segments[0].start == pytest.approx(1.0, abs=0.01)
        # Segments should be sequential
        assert result.segments[1].start >= result.segments[0].end - 0.01

    def test_tts_text_no_word_timestamps(self, generator: SubtitleGenerator) -> None:
        """tts_text path with no word timestamps creates single segment."""
        scenes = [self._make_scene(text="간단한 텍스트", tts_text="간단한 텍스트요")]
        tts_results = [self._make_tts_result(0, 2.0, 0.0, words=None)]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        assert len(result.segments) >= 1
        assert "간단한" in result.segments[0].text

    def test_scene_count_mismatch_logs_warning(self, generator: SubtitleGenerator) -> None:
        """Mismatched scene/result counts still produce output."""
        scenes = [self._make_scene("텍스트")]
        tts_results = [
            self._make_tts_result(
                0,
                2.0,
                0.0,
                words=[WordTimestamp(word="텍스트", start=0.0, end=2.0)],
            ),
            self._make_tts_result(
                1,
                2.0,
                2.0,
                words=[WordTimestamp(word="추가", start=0.0, end=2.0)],
            ),
        ]

        result = generator.generate_from_scene_results(scene_results=tts_results, scenes=scenes)

        # Should still produce segments despite mismatch
        assert len(result.segments) >= 1


class TestToSceneAss:
    """Test scene-based ASS file generation."""

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

    def test_to_ass_with_scene_styles_generates_valid_file(
        self,
        generator: SubtitleGenerator,
        tmp_path: Path,
    ) -> None:
        """to_ass_with_scene_styles produces a valid ASS file with scene styles."""

        subtitle = SubtitleFile(
            segments=[
                SubtitleSegment(index=1, start=0.0, end=1.0, text="Hello world"),
                SubtitleSegment(index=2, start=1.1, end=2.0, text="Second line"),
            ],
        )
        scenes = [
            Scene(
                scene_type=SceneType.HOOK,
                text="Hello world",
                visual_keyword="test",
            ),
            Scene(
                scene_type=SceneType.CONTENT,
                text="Second line",
                visual_keyword="test",
            ),
        ]
        scene_results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="hook",
                audio_path=tmp_path / "s0.mp3",
                duration_seconds=1.0,
                word_timestamps=None,
                start_offset=0.0,
            ),
            SceneTTSResult(
                scene_index=1,
                scene_type="content",
                audio_path=tmp_path / "s1.mp3",
                duration_seconds=1.0,
                word_timestamps=None,
                start_offset=1.1,
            ),
        ]

        output_path = tmp_path / "subtitle"
        result_path = generator.to_ass_with_scene_styles(
            subtitle=subtitle,
            output_path=output_path,
            scenes=scenes,
            scene_results=scene_results,
        )

        assert result_path.exists()
        assert result_path.suffix == ".ass"

        content = result_path.read_text()
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "Neutral" in content
        assert "Persona" in content
        assert "Emphasis" in content
        assert "[Events]" in content
        assert "Hello world" in content

    def test_to_ass_with_scene_styles_with_karaoke(
        self,
        generator: SubtitleGenerator,
        tmp_path: Path,
    ) -> None:
        """to_ass_with_scene_styles renders karaoke tags when words are provided."""
        words = [
            WordTimestamp(word="Hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.5, end=1.0),
        ]
        subtitle = SubtitleFile(
            segments=[
                SubtitleSegment(index=1, start=0.0, end=1.0, text="Hello world", words=words),
            ],
        )
        scenes = [
            Scene(
                scene_type=SceneType.CONTENT,
                text="Hello world",
                visual_keyword="test",
            ),
        ]
        scene_results = [
            SceneTTSResult(
                scene_index=0,
                scene_type="content",
                audio_path=tmp_path / "s0.mp3",
                duration_seconds=1.0,
                word_timestamps=words,
                start_offset=0.0,
            ),
        ]

        # Enable karaoke via config
        generator.config.highlight_current_word = True

        output_path = tmp_path / "sub_karaoke"
        result_path = generator.to_ass_with_scene_styles(
            subtitle=subtitle,
            output_path=output_path,
            scenes=scenes,
            scene_results=scene_results,
        )

        content = result_path.read_text()
        # Karaoke tags should be present
        assert "\\k" in content


class TestApplySceneStyling:
    """Test scene-based text styling."""

    @pytest.fixture
    def generator(
        self, subtitle_config: SubtitleConfig, composition_config: CompositionConfig
    ) -> SubtitleGenerator:
        return SubtitleGenerator(
            config=subtitle_config,
            composition_config=composition_config,
            template_loader=ASSTemplateLoader(),
        )

    def test_emphasis_words_highlighted(self, generator: SubtitleGenerator) -> None:
        """Emphasis words get ASS color tags when persona_style is provided."""
        from unittest.mock import MagicMock

        from app.models.scene import VisualStyle

        persona_style = MagicMock()
        persona_style.secondary_color = "#FF0000"

        result = generator._apply_scene_styling(
            text="이것은 중요한 포인트입니다",
            visual_style=VisualStyle.PERSONA,
            emphasis_words=["중요한"],
            persona_style=persona_style,
        )

        assert "\\c&H" in result  # ASS color tag applied

    def test_no_emphasis_without_persona_style(self, generator: SubtitleGenerator) -> None:
        """Without persona_style, emphasis words are not highlighted."""
        from app.models.scene import VisualStyle

        result = generator._apply_scene_styling(
            text="이것은 중요한 포인트입니다",
            visual_style=VisualStyle.NEUTRAL,
            emphasis_words=["중요한"],
            persona_style=None,
        )

        assert result == "이것은 중요한 포인트입니다"


class TestFindSceneIndex:
    """Test scene index lookup."""

    @pytest.fixture
    def generator(
        self, subtitle_config: SubtitleConfig, composition_config: CompositionConfig
    ) -> SubtitleGenerator:
        return SubtitleGenerator(
            config=subtitle_config,
            composition_config=composition_config,
            template_loader=ASSTemplateLoader(),
        )

    def test_finds_correct_scene(self, generator: SubtitleGenerator) -> None:
        timings = [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)]
        assert generator._find_scene_index(1.5, timings) == 0
        assert generator._find_scene_index(4.0, timings) == 1
        assert generator._find_scene_index(7.0, timings) == 2

    def test_end_of_last_scene(self, generator: SubtitleGenerator) -> None:
        timings = [(0.0, 3.0), (3.0, 6.0)]
        assert generator._find_scene_index(5.999, timings) == 1

    def test_beyond_last_scene_returns_last(self, generator: SubtitleGenerator) -> None:
        """Timestamps beyond last scene return last scene index (fallback)."""
        timings = [(0.0, 3.0)]
        assert generator._find_scene_index(10.0, timings) == 0

    def test_empty_timings(self, generator: SubtitleGenerator) -> None:
        assert generator._find_scene_index(1.0, []) == -1
