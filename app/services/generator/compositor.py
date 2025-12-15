"""FFmpeg-based video compositor.

Combines audio, visuals, and subtitles into final video output.
Supports template-based styling for visual effects and overlays.
"""

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.video import CompositionConfig
from app.services.generator.tts.base import TTSResult
from app.services.generator.visual.base import VisualAsset

if TYPE_CHECKING:
    from app.config.video_template import VideoTemplateConfig

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

    def __init__(
        self,
        config: CompositionConfig | None = None,
        template: "VideoTemplateConfig | None" = None,
    ) -> None:
        """Initialize FFmpegCompositor.

        Args:
            config: Composition configuration
            template: Video template for visual effects and overlays
        """
        self.config = config or CompositionConfig()
        self.template = template

    async def compose(
        self,
        audio: TTSResult,
        visuals: list[VisualAsset],
        subtitle_file: Path | None,
        output_path: Path,
        background_music_path: Path | None = None,
        title_text: str | None = None,
    ) -> CompositionResult:
        """Compose final video from components.

        Args:
            audio: TTS result with audio file
            visuals: List of visual assets
            subtitle_file: Path to subtitle file (ASS format)
            output_path: Output video path
            background_music_path: Optional background music
            title_text: Optional title text for overlay (상단 고정 제목)

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

            # Step 4: Add title overlay if configured
            if title_text and self._should_add_title_overlay():
                with_title = temp_path / "with_title.mp4"
                await self._add_title_overlay(
                    video_path=with_audio,
                    title_text=title_text,
                    output_path=with_title,
                )
                with_audio = with_title

            # Step 5: Burn subtitles
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

    def _should_use_frame_layout(self) -> bool:
        """Check if frame layout should be used.

        Returns:
            True if frame layout is enabled in template
        """
        if not self.template or not self.template.layout:
            return False
        return self.template.layout.frame.enabled

    async def _image_to_video(
        self,
        asset: VisualAsset,
        duration: float,
        segment_index: int,
        temp_dir: Path,
    ) -> Path:
        """Convert image to video segment with Ken Burns effect.

        Ken Burns effect is enabled based on template settings.
        If frame layout is enabled, image is placed in a centered frame.

        Args:
            asset: Image asset
            duration: Segment duration
            segment_index: Segment index
            temp_dir: Temp directory

        Returns:
            Path to video segment
        """
        if not asset.path:
            raise ValueError("Asset has no local path")

        output_path = temp_dir / f"segment_{segment_index}.mp4"

        # Check if frame layout should be used
        if self._should_use_frame_layout():
            # Use filter_complex for frame layout
            vf = self._build_frame_layout_filter(duration, segment_index)
            cmd = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(asset.path),
                "-t",
                str(duration),
                "-filter_complex",
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
        else:
            # Check if Ken Burns should be enabled from template
            enable_ken_burns = True  # Default
            if self.template and self.template.visual_effects:
                enable_ken_burns = self.template.visual_effects.ken_burns_enabled

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

    def _build_frame_layout_filter(
        self,
        duration: float,
        segment_index: int,
    ) -> str:
        """Build filter for frame layout (양산형 스타일).

        Creates a video with:
        - Solid/gradient background
        - Centered, smaller image with optional border
        - Ken Burns effect on the image

        Args:
            duration: Segment duration in seconds
            segment_index: Index for alternating zoom direction

        Returns:
            FFmpeg filter string
        """
        w = self.config.width
        h = self.config.height
        fps = self.config.fps
        total_frames = int(duration * fps)

        # Get frame layout settings
        frame_cfg = self.template.layout.frame
        bg_color = frame_cfg.background_color.lstrip("#")

        # Content area dimensions
        content_w = int(w * frame_cfg.content_width_ratio)
        content_h = int(h * frame_cfg.content_height_ratio)
        content_x = (w - content_w) // 2
        content_y = frame_cfg.content_y_offset

        # Get Ken Burns settings
        if self.template and self.template.visual_effects:
            vfx = self.template.visual_effects
            zoom_speed = vfx.ken_burns_zoom_speed
            start_scale = vfx.ken_burns_start_scale
            apply_color_grade = vfx.color_grading_enabled
            brightness = vfx.brightness
            contrast = vfx.contrast
            saturation = vfx.saturation
            warmth = vfx.warmth
        else:
            zoom_speed = 0.0005
            start_scale = 1.15
            apply_color_grade = True
            brightness = 0.05
            contrast = 1.1
            saturation = 1.2
            warmth = 0.1

        # Alternate zoom direction
        if segment_index % 2 == 0:
            zoom_expr = f"zoom+{zoom_speed}"
        else:
            zoom_expr = f"if(eq(on,1),{start_scale},zoom-{zoom_speed})"

        # Build complex filter:
        # 1. Scale image up for Ken Burns headroom
        # 2. Apply Ken Burns (zoompan)
        # 3. Color grading (optional)
        # 4. Create background
        # 5. Overlay image on background

        # Scale image and apply Ken Burns to content size
        image_filter = (
            f"scale=8000:-1,"
            f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={content_w}x{content_h}:fps={fps},"
            f"setsar=1"
        )

        # Add color grading
        if apply_color_grade:
            rs = warmth
            gs = warmth * 0.5
            bs = -warmth
            image_filter += (
                f",eq=brightness={brightness}:contrast={contrast}:saturation={saturation},"
                f"colorbalance=rs={rs}:gs={gs}:bs={bs}"
            )

        # Add border if enabled
        if frame_cfg.content_border_enabled:
            border_color = frame_cfg.content_border_color.lstrip("#")
            border_w = frame_cfg.content_border_width
            # Add padding (border) around image
            image_filter += f",pad={content_w + border_w * 2}:{content_h + border_w * 2}:{border_w}:{border_w}:color=#{border_color}"
            # Adjust position for border (center horizontally)
            content_x = (w - (content_w + border_w * 2)) // 2

        # Build gradient background if enabled
        if frame_cfg.background_gradient:
            top_color = frame_cfg.gradient_top_color.lstrip("#")
            bottom_color = frame_cfg.gradient_bottom_color.lstrip("#")
            # Create gradient using gradients filter
            bg_filter = (
                f"color=c=0x{top_color}:s={w}x{h}:d={duration}:r={fps},"
                f"format=rgba,"
                f"geq=r='lerp(0x{top_color[0:2]},0x{bottom_color[0:2]},Y/H)':"
                f"g='lerp(0x{top_color[2:4]},0x{bottom_color[2:4]},Y/H)':"
                f"b='lerp(0x{top_color[4:6]},0x{bottom_color[4:6]},Y/H)':a=255"
            )
        else:
            bg_filter = f"color=c=0x{bg_color}:s={w}x{h}:d={duration}:r={fps}"

        # Combine: create background, overlay content
        full_filter = (
            f"[0:v]{image_filter}[content];"
            f"{bg_filter}[bg];"
            f"[bg][content]overlay={content_x}:{content_y}:format=auto"
        )

        return full_filter

    async def _image_to_video_with_filter_complex(
        self,
        asset: VisualAsset,
        duration: float,
        segment_index: int,
        temp_dir: Path,
    ) -> Path:
        """Convert image to video using filter_complex for frame layout.

        Args:
            asset: Image asset
            duration: Segment duration
            segment_index: Segment index
            temp_dir: Temp directory

        Returns:
            Path to video segment
        """
        if not asset.path:
            raise ValueError("Asset has no local path")

        output_path = temp_dir / f"segment_{segment_index}.mp4"
        vf = self._build_frame_layout_filter(duration, segment_index)

        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(asset.path),
            "-t",
            str(duration),
            "-filter_complex",
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
    ) -> str:
        """Build Ken Burns zoom effect filter with optional color grading.

        Alternates between zoom-in and zoom-out based on segment index.
        Settings are read from template if available.

        Args:
            duration: Segment duration in seconds
            segment_index: Index to determine zoom direction

        Returns:
            FFmpeg filter string
        """
        w = self.config.width
        h = self.config.height
        fps = self.config.fps
        total_frames = int(duration * fps)

        # Get settings from template or use defaults
        if self.template and self.template.visual_effects:
            vfx = self.template.visual_effects
            zoom_speed = vfx.ken_burns_zoom_speed
            start_scale = vfx.ken_burns_start_scale
            apply_color_grade = vfx.color_grading_enabled
            brightness = vfx.brightness
            contrast = vfx.contrast
            saturation = vfx.saturation
            warmth = vfx.warmth
        else:
            # Legacy defaults
            zoom_speed = 0.0005
            start_scale = 1.15
            apply_color_grade = True
            brightness = 0.05
            contrast = 1.1
            saturation = 1.2
            warmth = 0.1

        # Alternate between zoom-in (even) and zoom-out (odd)
        if segment_index % 2 == 0:
            zoom_expr = f"zoom+{zoom_speed}"
        else:
            zoom_expr = f"if(eq(on,1),{start_scale},zoom-{zoom_speed})"

        # Scale up first (to allow room for zooming), then apply zoompan
        base_filter = (
            f"scale=8000:-1,"
            f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={w}x{h}:fps={fps},"
            f"setsar=1"
        )

        if apply_color_grade:
            # Add color grading from template settings
            # colorbalance: rs=red shadows, gs=green shadows, bs=blue shadows
            # warmth > 0 means more red, less blue
            rs = warmth
            gs = warmth * 0.5
            bs = -warmth
            color_grade = (
                f",eq=brightness={brightness}:contrast={contrast}:saturation={saturation},"
                f"colorbalance=rs={rs}:gs={gs}:bs={bs}"
            )
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

    def _should_add_title_overlay(self) -> bool:
        """Check if title overlay should be added based on template.

        Returns:
            True if title overlay is enabled in template
        """
        if not self.template or not self.template.layout:
            return False

        title_config = self.template.layout.title_overlay
        return title_config is not None and title_config.enabled

    def _resolve_font_path(self, font_name: str) -> str:
        """Resolve font name to actual file path.

        Searches for fonts in common locations:
        - User fonts: ~/.local/share/fonts/
        - System fonts: /usr/share/fonts/

        Args:
            font_name: Font name (e.g., "Noto Sans CJK KR")

        Returns:
            Path to font file, or fallback font if not found
        """
        import subprocess

        # Try to find font using fc-match
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", font_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                font_path = result.stdout.strip()
                if Path(font_path).exists():
                    logger.debug(f"Resolved font '{font_name}' to {font_path}")
                    return font_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: check common locations directly
        user_fonts_dir = Path.home() / ".local" / "share" / "fonts"
        system_fonts_dirs = [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
        ]

        # Map font names to possible file patterns
        font_patterns = {
            "Noto Sans CJK KR": ["NotoSansCJKkr-Bold.otf", "NotoSansCJKkr-Regular.otf"],
            "Pretendard-Bold": ["Pretendard-Bold.otf", "Pretendard-Bold.ttf"],
            "Pretendard": ["Pretendard-Regular.otf", "Pretendard-Regular.ttf"],
        }

        patterns = font_patterns.get(font_name, [f"{font_name}.otf", f"{font_name}.ttf"])

        # Search in user fonts first
        for pattern in patterns:
            font_path = user_fonts_dir / pattern
            if font_path.exists():
                logger.debug(f"Found font at {font_path}")
                return str(font_path)

        # Search in system fonts
        for fonts_dir in system_fonts_dirs:
            for pattern in patterns:
                for font_path in fonts_dir.rglob(pattern):
                    logger.debug(f"Found font at {font_path}")
                    return str(font_path)

        # Ultimate fallback
        fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        logger.warning(f"Font '{font_name}' not found, using fallback: {fallback}")
        return fallback

    async def _add_title_overlay(
        self,
        video_path: Path,
        title_text: str,
        output_path: Path,
    ) -> None:
        """Add title text overlay to video.

        Uses FFmpeg drawtext filter to add text at the top of the video.

        Args:
            video_path: Input video path
            title_text: Title text to display
            output_path: Output path
        """
        if not self.template or not self.template.layout:
            return

        title_config = self.template.layout.title_overlay
        if not title_config:
            return

        # Get settings from template
        # Note: font_name is not used yet; using system font path directly
        font_size = title_config.font_size
        font_color = title_config.color.lstrip("#")
        outline_color = title_config.outline_color.lstrip("#")
        outline_width = title_config.outline_width
        position_y = title_config.position_y

        # Build drawtext filter
        # Escape special characters in text
        escaped_text = title_text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")

        # Build filter with background box if enabled
        if title_config.background_enabled:
            bg_opacity = int(title_config.background_opacity * 255)
            bg_color = title_config.background_color.lstrip("#")
            box_filter = f":box=1:boxcolor={bg_color}@{bg_opacity / 255:.2f}:boxborderw=10"
        else:
            box_filter = ""

        # Resolve font path from template font_name
        font_path = self._resolve_font_path(title_config.font_name)

        drawtext_filter = (
            f"drawtext=text='{escaped_text}':"
            f"fontfile={font_path}:"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"borderw={outline_width}:"
            f"bordercolor={outline_color}:"
            f"x=(w-text_w)/2:"
            f"y={position_y}"
            f"{box_filter}"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            drawtext_filter,
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


__all__ = ["FFmpegCompositor", "CompositionResult"]
