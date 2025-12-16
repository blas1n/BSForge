"""Type-safe FFmpeg wrapper using ffmpeg-python.

This module provides a typed interface for FFmpeg operations,
replacing direct subprocess calls with the ffmpeg-python library
for better type safety and maintainability.
"""

from dataclasses import dataclass
from pathlib import Path

import ffmpeg

from app.core.logging import get_logger

logger = get_logger(__name__)


class FFmpegError(Exception):
    """FFmpeg operation failed."""

    def __init__(self, message: str, stderr: str | None = None) -> None:
        """Initialize FFmpeg error.

        Args:
            message: Error message
            stderr: FFmpeg stderr output
        """
        self.stderr = stderr
        super().__init__(message)


@dataclass
class ProbeResult:
    """Result of probing a media file.

    Attributes:
        duration: Duration in seconds
        width: Video width (if video stream exists)
        height: Video height (if video stream exists)
        fps: Frames per second (if video stream exists)
        has_video: Whether file has video stream
        has_audio: Whether file has audio stream
        format_name: Container format name
        bit_rate: Overall bit rate
    """

    duration: float
    width: int | None
    height: int | None
    fps: float | None
    has_video: bool
    has_audio: bool
    format_name: str
    bit_rate: int | None


class FFmpegWrapper:
    """Type-safe wrapper for FFmpeg operations.

    Provides a clean interface for common FFmpeg tasks with proper
    error handling and type annotations.

    Example:
        >>> wrapper = FFmpegWrapper()
        >>> info = await wrapper.probe("/path/to/video.mp4")
        >>> print(f"Duration: {info.duration}s")
    """

    def __init__(self, overwrite: bool = True, quiet: bool = True) -> None:
        """Initialize FFmpeg wrapper.

        Args:
            overwrite: Whether to overwrite output files
            quiet: Whether to suppress FFmpeg output
        """
        self.overwrite = overwrite
        self.quiet = quiet

    async def probe(self, input_path: Path | str) -> ProbeResult:
        """Probe a media file for information.

        Args:
            input_path: Path to media file

        Returns:
            ProbeResult with file information

        Raises:
            FFmpegError: If probing fails
        """
        try:
            probe_data = ffmpeg.probe(str(input_path))
        except ffmpeg.Error as e:
            raise FFmpegError(
                f"Failed to probe {input_path}",
                stderr=e.stderr.decode() if e.stderr else None,
            ) from e

        # Parse format info
        format_info = probe_data.get("format", {})
        duration = float(format_info.get("duration", 0))
        format_name = format_info.get("format_name", "unknown")
        bit_rate_str = format_info.get("bit_rate")
        bit_rate = int(bit_rate_str) if bit_rate_str else None

        # Find video and audio streams
        streams = probe_data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        width = None
        height = None
        fps = None

        if video_stream:
            width = video_stream.get("width")
            height = video_stream.get("height")
            # Parse frame rate (can be "30/1" or "30000/1001" format)
            fps_str = video_stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 0

        return ProbeResult(
            duration=duration,
            width=width,
            height=height,
            fps=fps,
            has_video=video_stream is not None,
            has_audio=audio_stream is not None,
            format_name=format_name,
            bit_rate=bit_rate,
        )

    async def get_duration(self, input_path: Path | str) -> float:
        """Get duration of a media file in seconds.

        Args:
            input_path: Path to media file

        Returns:
            Duration in seconds

        Raises:
            FFmpegError: If getting duration fails
        """
        result = await self.probe(input_path)
        return result.duration

    def image_to_video(
        self,
        image_path: Path | str,
        output_path: Path | str,
        duration: float,
        fps: int = 30,
        size: tuple[int, int] = (1080, 1920),
    ) -> ffmpeg.nodes.OutputStream:
        """Create a video from a static image.

        Args:
            image_path: Path to input image
            output_path: Path to output video
            duration: Video duration in seconds
            fps: Frames per second
            size: Output size (width, height)

        Returns:
            FFmpeg output stream (call .run() to execute)
        """
        width, height = size
        stream = (
            ffmpeg.input(str(image_path), loop=1, t=duration)
            .filter("scale", width, height, force_original_aspect_ratio="decrease")
            .filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")
            .filter("fps", fps=fps)
            .output(str(output_path), vcodec="libx264", pix_fmt="yuv420p", t=duration)
        )

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def image_to_video_with_effect(
        self,
        image_path: Path | str,
        output_path: Path | str,
        duration: float,
        effect: str = "zoompan",
        fps: int = 30,
        size: tuple[int, int] = (1080, 1920),
    ) -> ffmpeg.nodes.OutputStream:
        """Create a video from image with Ken Burns effect.

        Args:
            image_path: Path to input image
            output_path: Path to output video
            duration: Video duration in seconds
            effect: Effect type ("zoompan" for Ken Burns)
            fps: Frames per second
            size: Output size (width, height)

        Returns:
            FFmpeg output stream
        """
        width, height = size
        total_frames = int(duration * fps)

        if effect == "zoompan":
            # Ken Burns effect - zoom from 100% to 120%
            stream = (
                ffmpeg.input(str(image_path))
                .filter(
                    "zoompan",
                    z="min(zoom+0.001,1.2)",
                    d=total_frames,
                    s=f"{width}x{height}",
                    fps=fps,
                )
                .filter("fps", fps=fps)
                .output(str(output_path), vcodec="libx264", pix_fmt="yuv420p", t=duration)
            )
        else:
            # Fallback to static
            stream = self.image_to_video(image_path, output_path, duration, fps, size)
            return stream

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def concat_videos(
        self,
        input_paths: list[Path | str],
        output_path: Path | str,
        with_audio: bool = False,
    ) -> ffmpeg.nodes.OutputStream:
        """Concatenate multiple videos.

        Args:
            input_paths: List of input video paths
            output_path: Path to output video
            with_audio: Whether to include audio streams

        Returns:
            FFmpeg output stream
        """
        inputs = [ffmpeg.input(str(p)) for p in input_paths]

        if with_audio:
            # Concatenate video and audio
            stream = ffmpeg.concat(*inputs, v=1, a=1)
        else:
            # Video only
            stream = ffmpeg.concat(*inputs, v=1, a=0)

        stream = stream.output(str(output_path), vcodec="libx264", acodec="aac")

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def add_audio(
        self,
        video_path: Path | str,
        audio_path: Path | str,
        output_path: Path | str,
        audio_volume: float = 1.0,
    ) -> ffmpeg.nodes.OutputStream:
        """Add audio track to video.

        Args:
            video_path: Path to input video
            audio_path: Path to audio file
            output_path: Path to output video
            audio_volume: Audio volume multiplier

        Returns:
            FFmpeg output stream
        """
        video = ffmpeg.input(str(video_path))
        audio = ffmpeg.input(str(audio_path))

        if audio_volume != 1.0:
            audio = audio.filter("volume", audio_volume)

        stream = ffmpeg.output(
            video.video,
            audio.audio,
            str(output_path),
            vcodec="copy",
            acodec="aac",
            shortest=None,
        )

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def mix_audio(
        self,
        video_path: Path | str,
        bg_audio_path: Path | str,
        output_path: Path | str,
        main_volume: float = 1.0,
        bg_volume: float = 0.3,
    ) -> ffmpeg.nodes.OutputStream:
        """Mix background audio with video's existing audio.

        Args:
            video_path: Path to input video (with audio)
            bg_audio_path: Path to background audio
            output_path: Path to output video
            main_volume: Main audio volume
            bg_volume: Background audio volume

        Returns:
            FFmpeg output stream
        """
        video = ffmpeg.input(str(video_path))
        bg_audio = ffmpeg.input(str(bg_audio_path))

        # Apply volume filters
        main_audio = video.audio.filter("volume", main_volume)
        bg_audio_filtered = bg_audio.audio.filter("volume", bg_volume)

        # Mix audio streams
        mixed = ffmpeg.filter([main_audio, bg_audio_filtered], "amix", inputs=2, duration="first")

        stream = ffmpeg.output(
            video.video,
            mixed,
            str(output_path),
            vcodec="copy",
            acodec="aac",
        )

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def burn_subtitles(
        self,
        video_path: Path | str,
        subtitle_path: Path | str,
        output_path: Path | str,
        font_dir: str | None = None,
    ) -> ffmpeg.nodes.OutputStream:
        """Burn subtitles into video.

        Args:
            video_path: Path to input video
            subtitle_path: Path to subtitle file (ASS/SRT)
            output_path: Path to output video
            font_dir: Optional font directory for ASS subtitles

        Returns:
            FFmpeg output stream
        """
        video = ffmpeg.input(str(video_path))

        # Build subtitle filter string
        sub_path_escaped = str(subtitle_path).replace(":", r"\:")
        sub_filter = f"subtitles='{sub_path_escaped}'"
        if font_dir:
            font_dir_escaped = font_dir.replace(":", r"\:")
            sub_filter += f":fontsdir='{font_dir_escaped}'"

        stream = (
            video.filter("subtitles", str(subtitle_path), fontsdir=font_dir)
            if font_dir
            else video.filter("subtitles", str(subtitle_path))
        )

        stream = stream.output(str(output_path), vcodec="libx264", acodec="copy")

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def create_black_video(
        self,
        output_path: Path | str,
        duration: float,
        fps: int = 30,
        size: tuple[int, int] = (1080, 1920),
    ) -> ffmpeg.nodes.OutputStream:
        """Create a black video.

        Args:
            output_path: Path to output video
            duration: Video duration in seconds
            fps: Frames per second
            size: Output size (width, height)

        Returns:
            FFmpeg output stream
        """
        width, height = size
        stream = ffmpeg.input(
            f"color=black:s={width}x{height}:r={fps}", f="lavfi", t=duration
        ).output(str(output_path), vcodec="libx264", pix_fmt="yuv420p")

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    def apply_scale_and_colorgrade(
        self,
        video_path: Path | str,
        output_path: Path | str,
        size: tuple[int, int] = (1080, 1920),
        colorgrade: bool = True,
    ) -> ffmpeg.nodes.OutputStream:
        """Scale video and apply color grading.

        Args:
            video_path: Path to input video
            output_path: Path to output video
            size: Target size (width, height)
            colorgrade: Whether to apply color grading

        Returns:
            FFmpeg output stream
        """
        width, height = size
        video = ffmpeg.input(str(video_path))

        # Scale with padding
        stream = video.filter("scale", width, height, force_original_aspect_ratio="decrease")
        stream = stream.filter("pad", width, height, "(ow-iw)/2", "(oh-ih)/2")

        if colorgrade:
            # Simple color grading: slight contrast boost
            stream = stream.filter("eq", contrast=1.05, brightness=0.02, saturation=1.1)

        stream = stream.output(str(output_path), vcodec="libx264", pix_fmt="yuv420p")

        if self.overwrite:
            stream = stream.overwrite_output()

        return stream

    async def run(self, stream: ffmpeg.nodes.OutputStream) -> None:
        """Execute an FFmpeg stream.

        Args:
            stream: FFmpeg output stream to execute

        Raises:
            FFmpegError: If execution fails
        """
        try:
            if self.quiet:
                stream.run(quiet=True, capture_stderr=True)
            else:
                stream.run()
        except ffmpeg.Error as e:
            stderr = e.stderr.decode() if e.stderr else "Unknown error"
            logger.error("FFmpeg command failed", stderr=stderr, exc_info=True)
            raise FFmpegError(f"FFmpeg execution failed: {stderr}", stderr=stderr) from e

    def get_command(self, stream: ffmpeg.nodes.OutputStream) -> list[str]:
        """Get the FFmpeg command line arguments.

        Useful for debugging and logging.

        Args:
            stream: FFmpeg output stream

        Returns:
            List of command line arguments
        """
        result: list[str] = ffmpeg.compile(stream)
        return result

    async def run_raw(
        self,
        args: list[str],
        capture_output: bool = True,
    ) -> tuple[bytes, bytes]:
        """Run raw FFmpeg command (for complex operations).

        Args:
            args: FFmpeg command line arguments (without 'ffmpeg' prefix)
            capture_output: Whether to capture stdout/stderr

        Returns:
            Tuple of (stdout, stderr)

        Raises:
            FFmpegError: If execution fails
        """
        import asyncio

        cmd = ["ffmpeg"] + args
        logger.debug("Running raw FFmpeg command", cmd=" ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                stderr_str = stderr.decode() if stderr else "Unknown error"
                raise FFmpegError(
                    f"FFmpeg failed with code {process.returncode}", stderr=stderr_str
                )

            return stdout or b"", stderr or b""

        except FileNotFoundError as e:
            raise FFmpegError("FFmpeg not found. Please install FFmpeg.") from e


# Singleton instance
_wrapper: FFmpegWrapper | None = None


def get_ffmpeg_wrapper() -> FFmpegWrapper:
    """Get the singleton FFmpeg wrapper instance."""
    global _wrapper
    if _wrapper is None:
        _wrapper = FFmpegWrapper()
    return _wrapper


__all__ = [
    "FFmpegError",
    "FFmpegWrapper",
    "ProbeResult",
    "get_ffmpeg_wrapper",
]
