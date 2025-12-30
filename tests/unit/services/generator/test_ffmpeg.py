"""Tests for FFmpegWrapper."""

from unittest.mock import MagicMock, patch

import ffmpeg
import pytest

from app.services.generator.ffmpeg import (
    FFmpegError,
    FFmpegWrapper,
    ProbeResult,
)


class TestFFmpegError:
    """Tests for FFmpegError exception."""

    @pytest.mark.unit
    def test_ffmpeg_error_basic(self) -> None:
        """Test basic FFmpegError creation."""
        error = FFmpegError("Test error")

        assert str(error) == "Test error"
        assert error.stderr is None

    @pytest.mark.unit
    def test_ffmpeg_error_with_stderr(self) -> None:
        """Test FFmpegError with stderr output."""
        error = FFmpegError("Failed to encode", stderr="Invalid codec")

        assert str(error) == "Failed to encode"
        assert error.stderr == "Invalid codec"


class TestProbeResult:
    """Tests for ProbeResult dataclass."""

    @pytest.mark.unit
    def test_probe_result_full(self) -> None:
        """Test ProbeResult with all fields."""
        result = ProbeResult(
            duration=120.5,
            width=1920,
            height=1080,
            fps=30.0,
            has_video=True,
            has_audio=True,
            format_name="mp4",
            bit_rate=5000000,
        )

        assert result.duration == 120.5
        assert result.width == 1920
        assert result.height == 1080
        assert result.fps == 30.0
        assert result.has_video is True
        assert result.has_audio is True
        assert result.format_name == "mp4"
        assert result.bit_rate == 5000000

    @pytest.mark.unit
    def test_probe_result_audio_only(self) -> None:
        """Test ProbeResult for audio-only file."""
        result = ProbeResult(
            duration=180.0,
            width=None,
            height=None,
            fps=None,
            has_video=False,
            has_audio=True,
            format_name="mp3",
            bit_rate=320000,
        )

        assert result.width is None
        assert result.height is None
        assert result.fps is None
        assert result.has_video is False
        assert result.has_audio is True


class TestFFmpegWrapper:
    """Tests for FFmpegWrapper class."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.fixture
    def quiet_wrapper(self) -> FFmpegWrapper:
        """Create quiet FFmpegWrapper instance."""
        return FFmpegWrapper(overwrite=True, quiet=True)

    @pytest.mark.unit
    def test_init_defaults(self) -> None:
        """Test default initialization."""
        wrapper = FFmpegWrapper()

        assert wrapper.overwrite is True
        assert wrapper.quiet is True

    @pytest.mark.unit
    def test_init_custom(self) -> None:
        """Test custom initialization."""
        wrapper = FFmpegWrapper(overwrite=False, quiet=False)

        assert wrapper.overwrite is False
        assert wrapper.quiet is False


class TestProbe:
    """Tests for probe method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_probe_video_file(self, wrapper: FFmpegWrapper) -> None:
        """Test probing a video file."""
        mock_probe_data = {
            "format": {
                "duration": "120.5",
                "format_name": "mp4",
                "bit_rate": "5000000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                },
                {"codec_type": "audio"},
            ],
        }

        with patch("app.services.generator.ffmpeg.ffmpeg.probe", return_value=mock_probe_data):
            result = await wrapper.probe("/path/to/video.mp4")

        assert result.duration == 120.5
        assert result.width == 1920
        assert result.height == 1080
        assert result.fps == 30.0
        assert result.has_video is True
        assert result.has_audio is True
        assert result.format_name == "mp4"
        assert result.bit_rate == 5000000

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_probe_audio_file(self, wrapper: FFmpegWrapper) -> None:
        """Test probing an audio-only file."""
        mock_probe_data = {
            "format": {
                "duration": "180.0",
                "format_name": "mp3",
                "bit_rate": "320000",
            },
            "streams": [{"codec_type": "audio"}],
        }

        with patch("app.services.generator.ffmpeg.ffmpeg.probe", return_value=mock_probe_data):
            result = await wrapper.probe("/path/to/audio.mp3")

        assert result.duration == 180.0
        assert result.width is None
        assert result.height is None
        assert result.fps is None
        assert result.has_video is False
        assert result.has_audio is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_probe_fractional_fps(self, wrapper: FFmpegWrapper) -> None:
        """Test probing file with fractional frame rate."""
        mock_probe_data = {
            "format": {"duration": "60.0", "format_name": "mp4"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30000/1001",  # ~29.97 fps
                }
            ],
        }

        with patch("app.services.generator.ffmpeg.ffmpeg.probe", return_value=mock_probe_data):
            result = await wrapper.probe("/path/to/video.mp4")

        assert result.fps is not None
        assert 29.9 < result.fps < 30.0  # NTSC 29.97

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_probe_error(self, wrapper: FFmpegWrapper) -> None:
        """Test probe failure handling."""
        mock_error = ffmpeg.Error("ffmpeg", b"", b"File not found")

        with (
            patch("app.services.generator.ffmpeg.ffmpeg.probe", side_effect=mock_error),
            pytest.raises(FFmpegError) as exc_info,
        ):
            await wrapper.probe("/path/to/missing.mp4")

        assert "Failed to probe" in str(exc_info.value)


class TestGetDuration:
    """Tests for get_duration method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_duration(self, wrapper: FFmpegWrapper) -> None:
        """Test getting duration from file."""
        mock_probe_data = {
            "format": {"duration": "45.5", "format_name": "mp4"},
            "streams": [],
        }

        with patch("app.services.generator.ffmpeg.ffmpeg.probe", return_value=mock_probe_data):
            duration = await wrapper.get_duration("/path/to/video.mp4")

        assert duration == 45.5


class TestImageToVideo:
    """Tests for image_to_video method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_image_to_video_basic(self, wrapper: FFmpegWrapper) -> None:
        """Test basic image to video conversion."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.image_to_video(
                "/path/to/image.jpg",
                "/path/to/output.mp4",
                duration=10.0,
                size=(1080, 1920),
            )

        assert result is not None
        mock_input.assert_called_once()

    @pytest.mark.unit
    def test_image_to_video_custom_params(self, wrapper: FFmpegWrapper) -> None:
        """Test image to video with custom parameters."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.image_to_video(
                "/path/to/image.jpg",
                "/path/to/output.mp4",
                duration=5.0,
                size=(1080, 1920),
                fps=60,
            )

        assert result is not None


class TestImageToVideoWithEffect:
    """Tests for image_to_video_with_effect method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_zoompan_effect(self, wrapper: FFmpegWrapper) -> None:
        """Test Ken Burns zoompan effect."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.image_to_video_with_effect(
                "/path/to/image.jpg",
                "/path/to/output.mp4",
                duration=10.0,
                size=(1080, 1920),
                effect="zoompan",
            )

        assert result is not None

    @pytest.mark.unit
    def test_fallback_effect(self, wrapper: FFmpegWrapper) -> None:
        """Test fallback to static when unknown effect."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.image_to_video_with_effect(
                "/path/to/image.jpg",
                "/path/to/output.mp4",
                duration=10.0,
                size=(1080, 1920),
                effect="unknown",
            )

        assert result is not None


class TestConcatVideos:
    """Tests for concat_videos method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_concat_videos_without_audio(self, wrapper: FFmpegWrapper) -> None:
        """Test concatenating videos without audio."""
        input_paths = ["/path/to/video1.mp4", "/path/to/video2.mp4"]

        with (
            patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input,
            patch("app.services.generator.ffmpeg.ffmpeg.concat") as mock_concat,
        ):
            mock_stream = MagicMock()
            mock_input.return_value = mock_stream
            mock_concat.return_value.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.concat_videos(input_paths, "/path/to/output.mp4", with_audio=False)

        assert result is not None
        mock_concat.assert_called_once()

    @pytest.mark.unit
    def test_concat_videos_with_audio(self, wrapper: FFmpegWrapper) -> None:
        """Test concatenating videos with audio."""
        input_paths = ["/path/to/video1.mp4", "/path/to/video2.mp4"]

        with (
            patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input,
            patch("app.services.generator.ffmpeg.ffmpeg.concat") as mock_concat,
        ):
            mock_stream = MagicMock()
            mock_input.return_value = mock_stream
            mock_concat.return_value.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.concat_videos(input_paths, "/path/to/output.mp4", with_audio=True)

        assert result is not None


class TestAddAudio:
    """Tests for add_audio method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_add_audio_basic(self, wrapper: FFmpegWrapper) -> None:
        """Test adding audio to video."""
        with (
            patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input,
            patch("app.services.generator.ffmpeg.ffmpeg.output") as mock_output,
        ):
            mock_video = MagicMock()
            mock_audio = MagicMock()
            mock_input.side_effect = [mock_video, mock_audio]
            mock_stream = MagicMock()
            mock_output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.add_audio(
                "/path/to/video.mp4",
                "/path/to/audio.mp3",
                "/path/to/output.mp4",
            )

        assert result is not None

    @pytest.mark.unit
    def test_add_audio_with_volume(self, wrapper: FFmpegWrapper) -> None:
        """Test adding audio with volume adjustment."""
        with (
            patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input,
            patch("app.services.generator.ffmpeg.ffmpeg.output") as mock_output,
        ):
            mock_video = MagicMock()
            mock_audio = MagicMock()
            mock_input.side_effect = [mock_video, mock_audio]
            mock_stream = MagicMock()
            mock_audio.filter.return_value = mock_audio
            mock_output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.add_audio(
                "/path/to/video.mp4",
                "/path/to/audio.mp3",
                "/path/to/output.mp4",
                audio_volume=0.5,
            )

        assert result is not None


class TestMixAudio:
    """Tests for mix_audio method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_mix_audio(self, wrapper: FFmpegWrapper) -> None:
        """Test mixing background audio with video."""
        with (
            patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input,
            patch("app.services.generator.ffmpeg.ffmpeg.filter") as mock_filter,
            patch("app.services.generator.ffmpeg.ffmpeg.output") as mock_output,
        ):
            mock_video = MagicMock()
            mock_bg_audio = MagicMock()
            mock_input.side_effect = [mock_video, mock_bg_audio]
            mock_stream = MagicMock()
            mock_filter.return_value = mock_stream
            mock_output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.mix_audio(
                "/path/to/video.mp4",
                "/path/to/bg.mp3",
                "/path/to/output.mp4",
                main_volume=1.0,
                bg_volume=0.3,
            )

        assert result is not None


class TestBurnSubtitles:
    """Tests for burn_subtitles method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_burn_subtitles_basic(self, wrapper: FFmpegWrapper) -> None:
        """Test burning subtitles into video."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.burn_subtitles(
                "/path/to/video.mp4",
                "/path/to/subtitle.ass",
                "/path/to/output.mp4",
            )

        assert result is not None

    @pytest.mark.unit
    def test_burn_subtitles_with_font_dir(self, wrapper: FFmpegWrapper) -> None:
        """Test burning subtitles with custom font directory."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.burn_subtitles(
                "/path/to/video.mp4",
                "/path/to/subtitle.ass",
                "/path/to/output.mp4",
                font_dir="/path/to/fonts",
            )

        assert result is not None


class TestCreateBlackVideo:
    """Tests for create_black_video method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_create_black_video(self, wrapper: FFmpegWrapper) -> None:
        """Test creating black video."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.create_black_video(
                "/path/to/output.mp4",
                duration=5.0,
                size=(1080, 1920),
                fps=30,
            )

        assert result is not None


class TestApplyScaleAndColorgrade:
    """Tests for apply_scale_and_colorgrade method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_scale_and_colorgrade(self, wrapper: FFmpegWrapper) -> None:
        """Test scaling and color grading."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.apply_scale_and_colorgrade(
                "/path/to/video.mp4",
                "/path/to/output.mp4",
                size=(1080, 1920),
                colorgrade=True,
            )

        assert result is not None

    @pytest.mark.unit
    def test_scale_without_colorgrade(self, wrapper: FFmpegWrapper) -> None:
        """Test scaling without color grading."""
        with patch("app.services.generator.ffmpeg.ffmpeg.input") as mock_input:
            mock_stream = MagicMock()
            mock_input.return_value.filter.return_value = mock_stream
            mock_stream.filter.return_value = mock_stream
            mock_stream.output.return_value = mock_stream
            mock_stream.overwrite_output.return_value = mock_stream

            result = wrapper.apply_scale_and_colorgrade(
                "/path/to/video.mp4",
                "/path/to/output.mp4",
                size=(1080, 1920),
                colorgrade=False,
            )

        assert result is not None


class TestRun:
    """Tests for run method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_success(self, wrapper: FFmpegWrapper) -> None:
        """Test successful stream execution."""
        mock_stream = MagicMock()
        mock_stream.run = MagicMock()

        await wrapper.run(mock_stream)

        mock_stream.run.assert_called_once_with(quiet=True, capture_stderr=True)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_verbose(self) -> None:
        """Test verbose stream execution."""
        wrapper = FFmpegWrapper(quiet=False)
        mock_stream = MagicMock()
        mock_stream.run = MagicMock()

        await wrapper.run(mock_stream)

        mock_stream.run.assert_called_once_with()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_error(self, wrapper: FFmpegWrapper) -> None:
        """Test stream execution error handling."""
        mock_stream = MagicMock()
        mock_error = ffmpeg.Error("ffmpeg", b"", b"Encoding failed")
        mock_stream.run = MagicMock(side_effect=mock_error)

        with pytest.raises(FFmpegError) as exc_info:
            await wrapper.run(mock_stream)

        assert "FFmpeg execution failed" in str(exc_info.value)


class TestGetCommand:
    """Tests for get_command method."""

    @pytest.fixture
    def wrapper(self) -> FFmpegWrapper:
        """Create FFmpegWrapper instance."""
        return FFmpegWrapper()

    @pytest.mark.unit
    def test_get_command(self, wrapper: FFmpegWrapper) -> None:
        """Test getting FFmpeg command."""
        mock_stream = MagicMock()

        with patch(
            "app.services.generator.ffmpeg.ffmpeg.compile",
            return_value=["ffmpeg", "-i", "input.mp4", "output.mp4"],
        ):
            cmd = wrapper.get_command(mock_stream)

        assert cmd == ["ffmpeg", "-i", "input.mp4", "output.mp4"]


class TestDIIntegration:
    """Tests for DI container integration."""

    @pytest.mark.unit
    def test_ffmpeg_wrapper_instantiation(self) -> None:
        """Test FFmpegWrapper can be instantiated directly."""
        wrapper = FFmpegWrapper()

        assert isinstance(wrapper, FFmpegWrapper)
        assert wrapper.overwrite is True
        assert wrapper.quiet is True
