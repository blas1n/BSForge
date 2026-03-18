"""Unit tests for RemotionCompositor."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config.video import CompositionConfig
from app.config.video_template import (
    HeadlineConfig,
    LayoutConfig,
    SafeZoneConfig,
    SubtitleTemplateConfig,
    ThemeConfig,
    VideoTemplateConfig,
    VisualEffectsConfig,
)
from app.services.generator.remotion_compositor import RemotionCompositor


@pytest.fixture
def composition_config() -> CompositionConfig:
    return CompositionConfig(
        width=1080,
        height=1920,
        fps=30,
        background_music_volume=0.08,
    )


@pytest.fixture
def compositor(composition_config) -> RemotionCompositor:
    return RemotionCompositor(config=composition_config)


def _make_tts_result(duration: float = 5.0) -> MagicMock:
    r = MagicMock()
    r.duration_seconds = duration
    return r


def _make_scene_visual(duration: float = 5.0, start_offset: float = 0.0) -> MagicMock:
    asset = MagicMock()
    asset.path = MagicMock(spec=Path)
    asset.path.exists.return_value = True
    asset.is_video = False

    sv = MagicMock()
    sv.asset = asset
    sv.duration = duration
    sv.start_offset = start_offset
    return sv


class TestParseHeadline:
    """Tests for RemotionCompositor._parse_headline()."""

    def test_empty_string_returns_empty_tuple(self, compositor):
        line1, line2 = compositor._parse_headline("")
        assert line1 == ""
        assert line2 == ""

    def test_single_line_puts_all_in_line1(self, compositor):
        line1, line2 = compositor._parse_headline("AI가 세상을 바꾼다")
        assert line1 == "AI가 세상을 바꾼다"
        assert line2 == ""

    def test_two_lines_split_correctly(self, compositor):
        line1, line2 = compositor._parse_headline("이건 진짜 충격적\nAI가 인류를 바꾼다")
        assert line1 == "이건 진짜 충격적"
        assert line2 == "AI가 인류를 바꾼다"

    def test_multiple_newlines_only_first_split(self, compositor):
        line1, line2 = compositor._parse_headline("line1\nline2\nline3")
        assert line1 == "line1"
        assert line2 == "line2\nline3"

    def test_strips_whitespace(self, compositor):
        line1, line2 = compositor._parse_headline("  line1  \n  line2  ")
        assert line1 == "line1"
        assert line2 == "line2"


class TestBuildVisualAssets:
    """Tests for RemotionCompositor._build_visual_assets()."""

    def test_returns_empty_for_no_visuals(self, compositor):
        result = compositor._build_visual_assets([], VisualEffectsConfig())
        assert result == []

    def test_skips_assets_without_path(self, compositor):
        sv = MagicMock()
        sv.asset.path = None
        sv.duration = 5.0

        result = compositor._build_visual_assets([sv], VisualEffectsConfig())
        assert result == []

    def test_skips_assets_with_nonexistent_path(self, compositor):
        sv = MagicMock()
        sv.asset.path = MagicMock(spec=Path)
        sv.asset.path.exists.return_value = False
        sv.duration = 5.0

        result = compositor._build_visual_assets([sv], VisualEffectsConfig())
        assert result == []

    def test_includes_valid_image_asset(self, compositor):
        sv = _make_scene_visual(duration=5.0, start_offset=0.0)
        sv.asset.is_video = False
        sv.asset.path.__str__ = lambda self: "/tmp/image.jpg"

        result = compositor._build_visual_assets([sv], VisualEffectsConfig())

        assert len(result) == 1
        assert result[0]["type"] == "image"
        assert result[0]["duration"] == 5.0
        assert result[0]["start_time"] == 0.0

    def test_includes_valid_video_asset(self, compositor):
        sv = _make_scene_visual(duration=8.0, start_offset=2.0)
        sv.asset.is_video = True
        sv.asset.path.__str__ = lambda self: "/tmp/clip.mp4"

        result = compositor._build_visual_assets([sv], VisualEffectsConfig())

        assert len(result) == 1
        assert result[0]["type"] == "video"
        assert result[0]["duration"] == 8.0
        assert result[0]["start_time"] == 2.0

    def test_multiple_assets(self, compositor):
        sv1 = _make_scene_visual(duration=5.0, start_offset=0.0)
        sv1.asset.is_video = False
        sv1.asset.path.__str__ = lambda self: "/tmp/img1.jpg"

        sv2 = _make_scene_visual(duration=6.0, start_offset=5.0)
        sv2.asset.is_video = True
        sv2.asset.path.__str__ = lambda self: "/tmp/clip.mp4"

        result = compositor._build_visual_assets([sv1, sv2], VisualEffectsConfig())

        assert len(result) == 2


class TestBuildSubtitles:
    """Tests for RemotionCompositor._build_subtitles()."""

    def test_returns_empty_when_no_subtitle_data(self, compositor):
        result = compositor._build_subtitles(None, [])
        assert result == []

    def test_builds_segments_without_words(self, compositor):
        seg = MagicMock()
        seg.index = 1
        seg.start = 0.0
        seg.end = 2.5
        seg.text = "안녕하세요"
        seg.words = None

        subtitle_data = MagicMock()
        subtitle_data.segments = [seg]

        result = compositor._build_subtitles(subtitle_data, [])

        assert len(result) == 1
        assert result[0]["index"] == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 2.5
        assert result[0]["text"] == "안녕하세요"
        assert result[0]["words"] is None

    def test_builds_segments_with_word_timestamps(self, compositor):
        word = MagicMock()
        word.word = "안녕"
        word.start = 0.0
        word.end = 0.5

        seg = MagicMock()
        seg.index = 1
        seg.start = 0.0
        seg.end = 2.0
        seg.text = "안녕 세상"
        seg.words = [word]

        subtitle_data = MagicMock()
        subtitle_data.segments = [seg]

        result = compositor._build_subtitles(subtitle_data, [])

        assert result[0]["words"] == [{"word": "안녕", "start": 0.0, "end": 0.5}]

    def test_builds_multiple_segments(self, compositor):
        segments = []
        for i in range(3):
            seg = MagicMock()
            seg.index = i
            seg.start = float(i * 2)
            seg.end = float(i * 2 + 2)
            seg.text = f"segment {i}"
            seg.words = None
            segments.append(seg)

        subtitle_data = MagicMock()
        subtitle_data.segments = segments

        result = compositor._build_subtitles(subtitle_data, [])

        assert len(result) == 3


class TestStripAssTags:
    """Tests for RemotionCompositor._strip_ass_tags()."""

    def test_strips_color_tags(self):
        text = r"{\c&HC4CD4E&}버블 정렬{\c}로 {\c&HC4CD4E&}음악{\c}을 바꿉니다!"
        assert RemotionCompositor._strip_ass_tags(text) == "버블 정렬로 음악을 바꿉니다!"

    def test_preserves_plain_text(self):
        assert RemotionCompositor._strip_ass_tags("안녕하세요") == "안녕하세요"

    def test_strips_multiple_tag_types(self):
        text = r"{\b1}bold{\b0} and {\i1}italic{\i0}"
        assert RemotionCompositor._strip_ass_tags(text) == "bold and italic"

    def test_empty_string(self):
        assert RemotionCompositor._strip_ass_tags("") == ""


class TestBuildSubtitlesStripsAssTags:
    """Tests that _build_subtitles strips ASS tags from text."""

    def test_strips_ass_tags_from_segment_text(self, compositor):
        seg = MagicMock()
        seg.index = 1
        seg.start = 0.0
        seg.end = 2.0
        seg.text = r"{\c&HC4CD4E&}버블 정렬{\c}로 음악을 바꿉니다"
        seg.words = None

        subtitle_data = MagicMock()
        subtitle_data.segments = [seg]

        result = compositor._build_subtitles(subtitle_data, [])

        assert result[0]["text"] == "버블 정렬로 음악을 바꿉니다"


class TestStageAsset:
    """Tests for RemotionCompositor._stage_asset()."""

    def test_copies_file_to_public_dir(self, tmp_path):
        src = tmp_path / "audio.wav"
        src.write_bytes(b"fake audio")
        public_dir = tmp_path / "public" / "_render_1"
        public_dir.mkdir(parents=True)

        result = RemotionCompositor._stage_asset(src, public_dir, "audio", "_render_1")

        assert result == "_render_1/audio.wav"
        assert (public_dir / "audio.wav").exists()
        assert (public_dir / "audio.wav").read_bytes() == b"fake audio"

    def test_returns_empty_for_nonexistent_source(self, tmp_path):
        public_dir = tmp_path / "public" / "_render_1"
        public_dir.mkdir(parents=True)

        result = RemotionCompositor._stage_asset(
            tmp_path / "missing.wav", public_dir, "audio", "_render_1"
        )

        assert result == ""

    def test_preserves_file_extension(self, tmp_path):
        src = tmp_path / "image.png"
        src.write_bytes(b"fake png")
        public_dir = tmp_path / "public" / "_render_1"
        public_dir.mkdir(parents=True)

        result = RemotionCompositor._stage_asset(src, public_dir, "visual_0.0", "_render_1")

        assert result == "_render_1/visual_0.0.png"

    def test_does_not_overwrite_existing(self, tmp_path):
        src = tmp_path / "audio.wav"
        src.write_bytes(b"new data")
        public_dir = tmp_path / "public" / "_render_1"
        public_dir.mkdir(parents=True)

        existing = public_dir / "audio.wav"
        existing.write_bytes(b"old data")

        RemotionCompositor._stage_asset(src, public_dir, "audio", "_render_1")

        assert existing.read_bytes() == b"old data"


class TestRender:
    """Tests for RemotionCompositor._render()."""

    @pytest.mark.asyncio
    async def test_render_success(self, compositor, tmp_path):
        output_path = tmp_path / "output.mp4"

        # Simulate process that creates the output file
        async def mock_communicate():
            output_path.write_bytes(b"fake video")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await compositor._render(
                props_path=tmp_path / "props.json",
                output_path=output_path,
                total_duration=30.0,
            )

        assert result.video_path == output_path
        assert result.duration_seconds == 30.0
        assert result.resolution == "1080x1920"
        assert result.fps == 30
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_render_raises_on_nonzero_exit(self, compositor, tmp_path):
        output_path = tmp_path / "output.mp4"

        async def mock_communicate():
            return b"", b"Error: something went wrong"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = mock_communicate

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError, match="Remotion render failed"),
        ):
            await compositor._render(
                props_path=tmp_path / "props.json",
                output_path=output_path,
                total_duration=30.0,
            )

    @pytest.mark.asyncio
    async def test_render_raises_when_output_missing(self, compositor, tmp_path):
        output_path = tmp_path / "output.mp4"

        async def mock_communicate():
            # Does NOT create output file
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError, match="output file not found"),
        ):
            await compositor._render(
                props_path=tmp_path / "props.json",
                output_path=output_path,
                total_duration=30.0,
            )

    @pytest.mark.asyncio
    async def test_render_cmd_contains_remotion_args(self, compositor, tmp_path):
        output_path = tmp_path / "output.mp4"
        props_path = tmp_path / "props.json"

        async def mock_communicate():
            output_path.write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await compositor._render(props_path, output_path, 10.0)

        cmd_args = mock_exec.call_args.args
        assert "npx" in cmd_args
        assert "remotion" in cmd_args
        assert "render" in cmd_args
        assert "KoreanShorts" in cmd_args
        assert str(output_path) in cmd_args
        assert "--props" in cmd_args
        assert str(props_path) in cmd_args


class TestComposeScenes:
    """Tests for RemotionCompositor.compose_scenes()."""

    @pytest.mark.asyncio
    async def test_compose_scenes_writes_props_json(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(10.0), _make_tts_result(5.0)]
        scene_visuals = [_make_scene_visual(10.0), _make_scene_visual(5.0)]

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}

        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=scene_visuals,
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
            )

        assert written_props["duration_seconds"] == 15.0
        assert written_props["fps"] == 30
        assert "visuals" in written_props
        assert "subtitles" in written_props

    @pytest.mark.asyncio
    async def test_compose_scenes_cleans_up_props_file_on_success(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
            )

        # Props file should be cleaned up after render
        assert not (tmp_path / "remotion_props.json").exists()

    @pytest.mark.asyncio
    async def test_compose_scenes_cleans_up_props_file_on_failure(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        async def mock_communicate():
            return b"", b"render error"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = mock_communicate

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
            )

        # Props file should be cleaned up even on error
        assert not (tmp_path / "remotion_props.json").exists()

    @pytest.mark.asyncio
    async def test_compose_scenes_uses_persona_accent_color(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        persona_style = MagicMock()
        persona_style.accent_color = "#00FF00"

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}

        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
                persona_style=persona_style,
            )

        assert written_props["accent_color"] == "#00FF00"

    @pytest.mark.asyncio
    async def test_compose_scenes_default_accent_color(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}

        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
            )

        assert written_props["accent_color"] == "#FF69B4"


class TestBuildSafeZone:
    """Tests for RemotionCompositor._build_safe_zone()."""

    def test_returns_defaults_when_no_template(self):
        result = RemotionCompositor._build_safe_zone(None)

        assert result["top_px"] == 380
        assert result["bottom_px"] == 480
        assert result["left_px"] == 120
        assert result["right_px"] == 120

    def test_uses_template_safe_zone(self):
        template = VideoTemplateConfig(
            name="test",
            layout=LayoutConfig(
                safe_zone=SafeZoneConfig(
                    top_px=160,
                    bottom_px=480,
                    left_px=120,
                    right_px=120,
                    platform="tiktok",
                )
            ),
        )

        result = RemotionCompositor._build_safe_zone(template)

        assert result["top_px"] == 160
        assert result["bottom_px"] == 480

    def test_youtube_safe_zone(self):
        template = VideoTemplateConfig(
            name="test",
            layout=LayoutConfig(
                safe_zone=SafeZoneConfig(
                    top_px=380,
                    bottom_px=380,
                    left_px=60,
                    right_px=120,
                    platform="youtube",
                )
            ),
        )

        result = RemotionCompositor._build_safe_zone(template)

        assert result["top_px"] == 380
        assert result["bottom_px"] == 380
        assert result["left_px"] == 60
        assert result["right_px"] == 120


class TestBuildTheme:
    """Tests for RemotionCompositor._build_theme()."""

    def test_returns_defaults_when_no_template(self):
        result = RemotionCompositor._build_theme(None, None)

        assert result["accent_color"] == "#FF69B4"
        assert result["font_family"] == "Pretendard"
        assert result["headline_font_size_line1"] == 110
        assert result["subtitle_font_size"] == 100
        assert result["highlight_color"] == "#FFFF00"

    def test_uses_template_theme(self):
        template = VideoTemplateConfig(
            name="test",
            theme=ThemeConfig(
                accent_color="#00FF00",
                font_family="Noto Sans KR",
                subtitle_font_size=80,
            ),
        )

        result = RemotionCompositor._build_theme(template, None)

        assert result["accent_color"] == "#00FF00"
        assert result["font_family"] == "Noto Sans KR"
        assert result["subtitle_font_size"] == 80

    def test_persona_accent_overrides_template(self):
        template = VideoTemplateConfig(
            name="test",
            theme=ThemeConfig(accent_color="#00FF00"),
        )
        persona_style = MagicMock()
        persona_style.accent_color = "#FF0000"

        result = RemotionCompositor._build_theme(template, persona_style)

        assert result["accent_color"] == "#FF0000"

    def test_persona_accent_overrides_default(self):
        persona_style = MagicMock()
        persona_style.accent_color = "#AABBCC"

        result = RemotionCompositor._build_theme(None, persona_style)

        assert result["accent_color"] == "#AABBCC"

    def test_all_theme_fields_present(self):
        result = RemotionCompositor._build_theme(None, None)

        expected_fields = [
            "accent_color",
            "secondary_color",
            "font_family",
            "headline_font_size_line1",
            "headline_font_size_line2",
            "subtitle_font_size",
            "headline_bg_color",
            "headline_bg_opacity",
            "highlight_color",
            "text_color",
            "outline_color",
        ]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"


class TestComposeScenesWithSafeZoneAndTheme:
    """Tests that compose_scenes includes safe_zone and theme in props."""

    @pytest.mark.asyncio
    async def test_props_include_safe_zone_and_theme(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}

        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
            )

        # safe_zone and theme should always be present in props
        assert "safe_zone" in written_props
        assert written_props["safe_zone"]["top_px"] == 380
        assert written_props["safe_zone"]["bottom_px"] == 480

        assert "theme" in written_props
        assert written_props["theme"]["accent_color"] == "#FF69B4"
        assert written_props["theme"]["font_family"] == "Pretendard"

    @pytest.mark.asyncio
    async def test_props_with_custom_template(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        template = VideoTemplateConfig(
            name="custom",
            layout=LayoutConfig(
                safe_zone=SafeZoneConfig(top_px=160, bottom_px=480),
            ),
            theme=ThemeConfig(
                accent_color="#00BFFF",
                font_family="Noto Sans KR",
            ),
        )

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}

        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
                video_template=template,
            )

        assert written_props["safe_zone"]["top_px"] == 160
        assert written_props["theme"]["accent_color"] == "#00BFFF"
        assert written_props["theme"]["font_family"] == "Noto Sans KR"


class TestBuildVisualAssetsWithCameraAndTransitions:
    """Tests that _build_visual_assets includes camera_movement and transitions."""

    def test_default_camera_movement(self, compositor):
        sv = _make_scene_visual(duration=5.0, start_offset=0.0)
        sv.asset.is_video = False
        sv.asset.path.__str__ = lambda self: "/tmp/img.jpg"
        vfx = VisualEffectsConfig()

        result = compositor._build_visual_assets([sv], vfx)

        assert len(result) == 1
        assert result[0]["camera_movement"] == "ken_burns"
        assert result[0]["transition_in"] == "none"  # first visual has no transition_in
        assert result[0]["transition_out"] == "flash"

    def test_custom_camera_movement(self, compositor):
        sv = _make_scene_visual(duration=5.0, start_offset=0.0)
        sv.asset.is_video = False
        sv.asset.path.__str__ = lambda self: "/tmp/img.jpg"
        vfx = VisualEffectsConfig(camera_movement="pan_left", transition_type="crossfade")

        result = compositor._build_visual_assets([sv], vfx)

        assert result[0]["camera_movement"] == "pan_left"
        assert result[0]["transition_out"] == "crossfade"

    def test_second_visual_has_transition_in(self, compositor):
        sv1 = _make_scene_visual(duration=5.0, start_offset=0.0)
        sv1.asset.is_video = False
        sv1.asset.path.__str__ = lambda self: "/tmp/img1.jpg"

        sv2 = _make_scene_visual(duration=5.0, start_offset=5.0)
        sv2.asset.is_video = False
        sv2.asset.path.__str__ = lambda self: "/tmp/img2.jpg"

        vfx = VisualEffectsConfig(transition_type="slide_left")

        result = compositor._build_visual_assets([sv1, sv2], vfx)

        assert result[0]["transition_in"] == "none"
        assert result[1]["transition_in"] == "slide_left"

    def test_randomize_camera_picks_from_options(self, compositor):
        sv = _make_scene_visual(duration=5.0, start_offset=0.0)
        sv.asset.is_video = False
        sv.asset.path.__str__ = lambda self: "/tmp/img.jpg"

        vfx = VisualEffectsConfig(
            randomize_camera=True,
            camera_movement_options=["pan_left", "pan_right"],
        )

        result = compositor._build_visual_assets([sv], vfx)

        assert result[0]["camera_movement"] in ["pan_left", "pan_right"]


class TestBuildSubtitlesWithAnimation:
    """Tests that _build_subtitles includes text_animation field."""

    def test_default_text_animation(self, compositor):
        seg = MagicMock()
        seg.index = 1
        seg.start = 0.0
        seg.end = 2.0
        seg.text = "안녕하세요"
        seg.words = None

        subtitle_data = MagicMock()
        subtitle_data.segments = [seg]

        result = compositor._build_subtitles(subtitle_data, [])

        assert result[0]["text_animation"] == "fade_in"

    def test_custom_text_animation(self, compositor):
        seg = MagicMock()
        seg.index = 1
        seg.start = 0.0
        seg.end = 2.0
        seg.text = "안녕하세요"
        seg.words = None

        subtitle_data = MagicMock()
        subtitle_data.segments = [seg]

        result = compositor._build_subtitles(subtitle_data, [], text_animation="bounce")

        assert result[0]["text_animation"] == "bounce"


class TestComposeScenesWithNewProps:
    """Tests that compose_scenes includes headline_animation and camera/transition props."""

    @pytest.mark.asyncio
    async def test_props_include_headline_animation(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        template = VideoTemplateConfig(
            name="test",
            layout=LayoutConfig(
                headline=HeadlineConfig(headline_animation="bounce"),
            ),
        )

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}
        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
                video_template=template,
            )

        assert written_props["headline_animation"] == "bounce"

    @pytest.mark.asyncio
    async def test_default_headline_animation(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}
        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
            )

        assert written_props["headline_animation"] == "fade_in"

    @pytest.mark.asyncio
    async def test_props_use_template_text_animation(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]

        template = VideoTemplateConfig(
            name="test",
            subtitle=SubtitleTemplateConfig(text_animation="pop"),
        )

        seg = MagicMock()
        seg.index = 1
        seg.start = 0.0
        seg.end = 2.0
        seg.text = "test"
        seg.words = None

        subtitle_data = MagicMock()
        subtitle_data.segments = [seg]

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}
        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=[],
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
                subtitle_data=subtitle_data,
                video_template=template,
            )

        assert written_props["subtitles"][0]["text_animation"] == "pop"

    @pytest.mark.asyncio
    async def test_props_include_camera_movement_in_visuals(self, compositor, tmp_path):
        output_path = tmp_path / "video"
        tts_results = [_make_tts_result(5.0)]
        scene_visuals = [_make_scene_visual(5.0, 0.0)]

        template = VideoTemplateConfig(
            name="test",
            visual_effects=VisualEffectsConfig(
                camera_movement="pan_left",
                transition_type="crossfade",
            ),
        )

        async def mock_communicate():
            (tmp_path / "video.mp4").write_bytes(b"data")
            return b"", b""

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = mock_communicate

        written_props: dict = {}
        original_write_text = Path.write_text

        def capture_write_text(self, data, *args, **kwargs):
            if self.name == "remotion_props.json":
                written_props.update(json.loads(data))
            return original_write_text(self, data, *args, **kwargs)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch.object(Path, "write_text", capture_write_text),
        ):
            await compositor.compose_scenes(
                scenes=[],
                scene_tts_results=tts_results,
                scene_visuals=scene_visuals,
                combined_audio_path=tmp_path / "audio.mp3",
                subtitle_file=None,
                output_path=output_path,
                video_template=template,
            )

        assert len(written_props["visuals"]) == 1
        assert written_props["visuals"][0]["camera_movement"] == "pan_left"
        assert written_props["visuals"][0]["transition_out"] == "crossfade"


class TestBuildSceneMetadata:
    """Tests for RemotionCompositor._build_scene_metadata()."""

    def _make_scene(
        self,
        scene_type: str = "content",
        visual_style: str = "neutral",
        transition_in: str = "fade",
        transition_out: str = "fade",
        emphasis_words: list | None = None,
    ) -> MagicMock:
        scene = MagicMock()
        scene.scene_type.value = scene_type
        scene.inferred_visual_style.value = visual_style
        scene.transition_in.value = transition_in
        scene.transition_out.value = transition_out
        scene.emphasis_words = emphasis_words or []
        return scene

    def _make_tts(self, duration: float = 3.0) -> MagicMock:
        r = MagicMock()
        r.duration_seconds = duration
        return r

    def test_empty_scenes(self):
        result = RemotionCompositor._build_scene_metadata([], [])
        assert result == []

    def test_single_scene(self):
        scene = self._make_scene(scene_type="hook", visual_style="neutral")
        tts = self._make_tts(5.0)

        result = RemotionCompositor._build_scene_metadata([scene], [tts])

        assert len(result) == 1
        assert result[0]["index"] == 0
        assert result[0]["scene_type"] == "hook"
        assert result[0]["visual_style"] == "neutral"
        assert result[0]["start_time"] == 0.0
        assert result[0]["duration"] == 5.0

    def test_cumulative_timing(self):
        scenes = [
            self._make_scene(scene_type="hook"),
            self._make_scene(scene_type="content"),
            self._make_scene(scene_type="conclusion"),
        ]
        tts_results = [self._make_tts(3.0), self._make_tts(5.0), self._make_tts(2.0)]

        result = RemotionCompositor._build_scene_metadata(scenes, tts_results)

        assert result[0]["start_time"] == 0.0
        assert result[1]["start_time"] == 3.0
        assert result[2]["start_time"] == 8.0

    def test_transitions_included(self):
        scene = self._make_scene(transition_in="flash", transition_out="slide")
        tts = self._make_tts()

        result = RemotionCompositor._build_scene_metadata([scene], [tts])

        assert result[0]["transition_in"] == "flash"
        assert result[0]["transition_out"] == "slide"

    def test_emphasis_words_included(self):
        scene = self._make_scene(emphasis_words=["진짜", "5분의 1"])
        tts = self._make_tts()

        result = RemotionCompositor._build_scene_metadata([scene], [tts])

        assert result[0]["emphasis_words"] == ["진짜", "5분의 1"]

    def test_handles_missing_tts_results(self):
        scenes = [self._make_scene(), self._make_scene()]
        tts_results = [self._make_tts(4.0)]  # only 1 tts for 2 scenes

        result = RemotionCompositor._build_scene_metadata(scenes, tts_results)

        assert result[0]["duration"] == 4.0
        assert result[1]["duration"] == 0.0
        assert result[1]["start_time"] == 4.0
