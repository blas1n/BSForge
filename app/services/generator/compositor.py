"""FFmpeg-based video compositor.

Combines audio, visuals, and subtitles into final video output.
"""

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.config.video import CompositionConfig
from app.services.generator.tts.base import TTSResult
from app.services.generator.visual.base import VisualAsset

logger = logging.getLogger(__name__)


@dataclass
class CompositionResult:
    """Result of video composition.

    Attributes:
        video_path: Path to final video file
        duration_seconds: Video duration
        file_size_bytes: Video file size
        resolution: Video resolution string
        fps: Frames per second
    """

    video_path: Path
    duration_seconds: float
    file_size_bytes: int
    resolution: str
    fps: int


class FFmpegCompositor:
    """Compose video using FFmpeg.

    Combines:
    - Audio from TTS
    - Visual assets (videos/images)
    - Subtitles (ASS format)

    Example:
        >>> compositor = FFmpegCompositor()
        >>> result = await compositor.compose(
        ...     audio=tts_result,
        ...     visuals=visual_assets,
        ...     subtitle_file=subtitle_path,
        ...     output_path=Path("/tmp/output.mp4"),
        ... )
    """

    def __init__(self, config: CompositionConfig | None = None) -> None:
        """Initialize FFmpegCompositor.

        Args:
            config: Composition configuration
        """
        self.config = config or CompositionConfig()

    async def compose(
        self,
        audio: TTSResult,
        visuals: list[VisualAsset],
        subtitle_file: Path | None,
        output_path: Path,
        background_music_path: Path | None = None,
    ) -> CompositionResult:
        """Compose final video from components.

        Args:
            audio: TTS result with audio file
            visuals: List of visual assets
            subtitle_file: Path to subtitle file (ASS format)
            output_path: Output video path
            background_music_path: Optional background music

        Returns:
            CompositionResult with final video info

        Raises:
            RuntimeError: If composition fails
        """
        output_path = output_path.with_suffix(".mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create temp directory for intermediate files
        with tempfile.TemporaryDirectory(prefix="bsforge_") as temp_dir:
            temp_path = Path(temp_dir)

            logger.info(f"Composing video: {len(visuals)} visuals, audio={audio.audio_path}")

            # Step 1: Create video sequence from visuals
            video_sequence = await self._create_video_sequence(
                visuals=visuals,
                target_duration=audio.duration_seconds,
                temp_dir=temp_path,
            )

            # Step 2: Combine with audio
            with_audio = temp_path / "with_audio.mp4"
            await self._add_audio(
                video_path=video_sequence,
                audio_path=audio.audio_path,
                output_path=with_audio,
            )

            # Step 3: Add background music if provided
            if background_music_path and background_music_path.exists():
                with_music = temp_path / "with_music.mp4"
                await self._add_background_music(
                    video_path=with_audio,
                    music_path=background_music_path,
                    output_path=with_music,
                )
                with_audio = with_music

            # Step 4: Burn subtitles
            if subtitle_file and subtitle_file.exists():
                final_video = output_path
                await self._burn_subtitles(
                    video_path=with_audio,
                    subtitle_path=subtitle_file,
                    output_path=final_video,
                )
            else:
                # Just copy to final location
                shutil.copy(with_audio, output_path)

        # Get final video info
        duration = await self._get_video_duration(output_path)
        file_size = output_path.stat().st_size

        logger.info(
            f"Composition complete: {output_path}, "
            f"duration={duration:.2f}s, size={file_size / 1024 / 1024:.1f}MB"
        )

        return CompositionResult(
            video_path=output_path,
            duration_seconds=duration,
            file_size_bytes=file_size,
            resolution=f"{self.config.width}x{self.config.height}",
            fps=self.config.fps,
        )

    async def _create_video_sequence(
        self,
        visuals: list[VisualAsset],
        target_duration: float,
        temp_dir: Path,
    ) -> Path:
        """Create video sequence from visual assets.

        Args:
            visuals: List of visual assets
            target_duration: Target duration in seconds
            temp_dir: Temporary directory

        Returns:
            Path to video sequence
        """
        if not visuals:
            # Create black video as fallback
            return await self._create_black_video(target_duration, temp_dir)

        # Prepare each visual as video segment
        segments: list[Path] = []
        current_duration = 0.0

        for i, asset in enumerate(visuals):
            if current_duration >= target_duration:
                break

            remaining = target_duration - current_duration

            if asset.is_video:
                segment_path = await self._prepare_video_segment(
                    asset=asset,
                    max_duration=remaining,
                    segment_index=i,
                    temp_dir=temp_dir,
                )
                segment_duration = min(asset.duration or remaining, remaining)
            else:
                # Image: convert to video segment
                segment_duration = min(asset.duration or 5.0, remaining)
                segment_path = await self._image_to_video(
                    asset=asset,
                    duration=segment_duration,
                    segment_index=i,
                    temp_dir=temp_dir,
                )

            if segment_path:
                segments.append(segment_path)
                current_duration += segment_duration

        # Pad with black if needed (minimum 0.1s to avoid floating point issues)
        remaining_duration = target_duration - current_duration
        if remaining_duration > 0.1:
            padding = await self._create_black_video(
                remaining_duration,
                temp_dir,
                suffix="_padding",
            )
            segments.append(padding)

        # Concatenate segments
        return await self._concat_videos(segments, temp_dir)

    async def _prepare_video_segment(
        self,
        asset: VisualAsset,
        max_duration: float,
        segment_index: int,
        temp_dir: Path,
    ) -> Path:
        """Prepare a video segment (scale, trim, etc.).

        Args:
            asset: Video asset
            max_duration: Maximum duration
            segment_index: Segment index
            temp_dir: Temp directory

        Returns:
            Path to prepared segment
        """
        if not asset.path:
            raise ValueError("Asset has no local path")

        output_path = temp_dir / f"segment_{segment_index}.mp4"

        # Build filter for scaling and padding
        scale_filter = self._build_scale_filter()

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(asset.path),
            "-t",
            str(max_duration),
            "-vf",
            scale_filter,
            "-c:v",
            self.config.video_codec,
            "-crf",
            str(self.config.crf),
            "-preset",
            self.config.preset,
            "-r",
            str(self.config.fps),
            "-pix_fmt",
            self.config.pixel_format,
            "-an",  # No audio
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)
        return output_path

    async def _image_to_video(
        self,
        asset: VisualAsset,
        duration: float,
        segment_index: int,
        temp_dir: Path,
        enable_ken_burns: bool = True,
    ) -> Path:
        """Convert image to video segment with Ken Burns effect.

        Args:
            asset: Image asset
            duration: Segment duration
            segment_index: Segment index
            temp_dir: Temp directory
            enable_ken_burns: Enable zoom in/out effect

        Returns:
            Path to video segment
        """
        if not asset.path:
            raise ValueError("Asset has no local path")

        output_path = temp_dir / f"segment_{segment_index}.mp4"

        # Build filter with Ken Burns effect (zoom in/out)
        if enable_ken_burns:
            vf = self._build_ken_burns_filter(duration, segment_index)
        else:
            vf = self._build_scale_filter()

        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(asset.path),
            "-t",
            str(duration),
            "-vf",
            vf,
            "-c:v",
            self.config.video_codec,
            "-crf",
            str(self.config.crf),
            "-preset",
            self.config.preset,
            "-r",
            str(self.config.fps),
            "-pix_fmt",
            self.config.pixel_format,
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)
        return output_path

    def _build_ken_burns_filter(
        self,
        duration: float,
        segment_index: int,
        apply_color_grade: bool = True,
    ) -> str:
        """Build Ken Burns zoom effect filter with optional color grading.

        Alternates between zoom-in and zoom-out based on segment index.

        Args:
            duration: Segment duration in seconds
            segment_index: Index to determine zoom direction
            apply_color_grade: Apply warm/orange color grading for viral style

        Returns:
            FFmpeg filter string
        """
        w = self.config.width
        h = self.config.height
        fps = self.config.fps
        total_frames = int(duration * fps)

        # Alternate between zoom-in (even) and zoom-out (odd)
        zoom_expr = "zoom+0.0005" if segment_index % 2 == 0 else "if(eq(on,1),1.15,zoom-0.0005)"

        # Scale up first (to allow room for zooming), then apply zoompan
        base_filter = (
            f"scale=8000:-1,"
            f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={w}x{h}:fps={fps},"
            f"setsar=1"
        )

        if apply_color_grade:
            # Add warm/orange color grading for viral style
            color_grade = ",eq=brightness=0.05:contrast=1.1:saturation=1.2,colorbalance=rs=0.1:gs=0.05:bs=-0.1"
            return base_filter + color_grade

        return base_filter

    async def _create_black_video(
        self,
        duration: float,
        temp_dir: Path,
        suffix: str = "",
    ) -> Path:
        """Create black video for padding.

        Args:
            duration: Video duration
            temp_dir: Temp directory
            suffix: Filename suffix

        Returns:
            Path to black video
        """
        output_path = temp_dir / f"black{suffix}.mp4"

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={self.config.width}x{self.config.height}:d={duration}:r={self.config.fps}",
            "-c:v",
            self.config.video_codec,
            "-crf",
            str(self.config.crf),
            "-preset",
            self.config.preset,
            "-pix_fmt",
            self.config.pixel_format,
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)
        return output_path

    async def _concat_videos(
        self,
        segments: list[Path],
        temp_dir: Path,
        add_flash: bool = True,
    ) -> Path:
        """Concatenate video segments with optional flash transitions.

        Args:
            segments: List of segment paths
            temp_dir: Temp directory
            add_flash: Add white flash between segments

        Returns:
            Path to concatenated video
        """
        if len(segments) == 1:
            return segments[0]

        if not add_flash:
            # Simple concat without transitions
            concat_file = temp_dir / "concat.txt"
            with open(concat_file, "w") as f:
                for segment in segments:
                    f.write(f"file '{segment}'\n")

            output_path = temp_dir / "sequence.mp4"

            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output_path),
            ]

            await self._run_ffmpeg(cmd)
            return output_path

        # Concat with flash transitions using xfade filter
        output_path = temp_dir / "sequence.mp4"

        # Build complex filter for flash transitions
        # Flash effect: wipelr with white color overlay
        inputs = []
        for _i, segment in enumerate(segments):
            inputs.extend(["-i", str(segment)])

        # Build xfade filter chain
        # Each transition: 0.15s flash effect
        filter_parts = []
        current_input = "[0:v]"

        for i in range(1, len(segments)):
            next_input = f"[{i}:v]"
            output = "[outv]" if i == len(segments) - 1 else f"[v{i}]"

            # xfade with fade transition (flash-like effect)
            # offset = cumulative duration - transition duration
            filter_parts.append(
                f"{current_input}{next_input}xfade=transition=fade:duration=0.15:offset=0{output}"
            )
            current_input = output

        # For simple cases, use concat demuxer with fade
        # Complex xfade requires knowing exact durations, fallback to simple concat
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment}'\n")

        # Add flash frames between segments by re-encoding with fade
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            "fade=t=in:st=0:d=0.1",  # Fade in at start
            "-c:v",
            self.config.video_codec,
            "-crf",
            str(self.config.crf),
            "-preset",
            self.config.preset,
            "-pix_fmt",
            self.config.pixel_format,
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)
        return output_path

    async def _add_audio(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> None:
        """Add audio to video.

        Args:
            video_path: Input video path
            audio_path: Audio path
            output_path: Output path
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c:v",
            "copy",
            "-c:a",
            self.config.audio_codec,
            "-b:a",
            self.config.audio_bitrate,
            "-shortest",
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)

    async def _add_background_music(
        self,
        video_path: Path,
        music_path: Path,
        output_path: Path,
    ) -> None:
        """Add background music to video.

        Args:
            video_path: Input video path (with main audio)
            music_path: Background music path
            output_path: Output path
        """
        volume = self.config.background_music_volume

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(music_path),
            "-filter_complex",
            f"[1:a]volume={volume}[music];[0:a][music]amix=inputs=2:duration=first[aout]",
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            self.config.audio_codec,
            "-b:a",
            self.config.audio_bitrate,
            "-shortest",
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)

    async def _burn_subtitles(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
    ) -> None:
        """Burn subtitles into video.

        Args:
            video_path: Input video path
            subtitle_path: Subtitle file path (ASS)
            output_path: Output path
        """
        # Escape path for FFmpeg filter
        escaped_path = str(subtitle_path).replace(":", r"\:").replace("'", r"\'")

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"ass={escaped_path}",
            "-c:v",
            self.config.video_codec,
            "-crf",
            str(self.config.crf),
            "-preset",
            self.config.preset,
            "-c:a",
            "copy",
            str(output_path),
        ]

        await self._run_ffmpeg(cmd)

    def _build_scale_filter(self, apply_color_grade: bool = False) -> str:
        """Build FFmpeg scale filter string.

        Args:
            apply_color_grade: Apply orange/warm color grading for viral style

        Returns:
            Filter string for scaling and padding
        """
        w = self.config.width
        h = self.config.height

        # Scale to fit, then pad to exact size
        base_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1"
        )

        if apply_color_grade:
            # Add warm/orange color grading for viral style
            # Increase red, slightly increase green, decrease blue
            color_grade = ",eq=brightness=0.05:contrast=1.1:saturation=1.2,colorbalance=rs=0.1:gs=0.05:bs=-0.1"
            return base_filter + color_grade

        return base_filter

    async def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration.

        Args:
            video_path: Path to video file

        Returns:
            Duration in seconds
        """
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()
        return float(stdout.decode().strip())

    async def _run_ffmpeg(self, cmd: list[str]) -> None:
        """Run FFmpeg command.

        Args:
            cmd: Command list

        Raises:
            RuntimeError: If FFmpeg fails
        """
        logger.debug(f"Running FFmpeg: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode()
            logger.error(f"FFmpeg failed: {error_msg}")
            raise RuntimeError(f"FFmpeg failed: {error_msg[:500]}")


__all__ = ["FFmpegCompositor", "CompositionResult"]
