"""FFmpeg-based video compositor.

Combines audio, visuals, and subtitles into final video output.
Supports template-based styling for visual effects and overlays.
Supports scene-based composition with per-scene visual styles.
"""

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.video import CompositionConfig
from app.core.logging import get_logger
from app.infrastructure.fonts import find_font_by_name
from app.services.generator.ffmpeg import FFmpegWrapper, get_ffmpeg_wrapper
from app.services.generator.tts.base import TTSResult
from app.services.generator.visual.base import VisualAsset

if TYPE_CHECKING:
    from app.config.persona import PersonaStyleConfig
    from app.config.video_template import VideoTemplateConfig
    from app.models.scene import Scene, VisualStyle
    from app.services.generator.tts.base import SceneTTSResult
    from app.services.generator.visual.manager import SceneVisualResult

logger = get_logger(__name__)


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
        ffmpeg_wrapper: FFmpegWrapper | None = None,
    ) -> None:
        """Initialize FFmpegCompositor.

        Args:
            config: Composition configuration
            template: Video template for visual effects and overlays
            ffmpeg_wrapper: FFmpeg wrapper for type-safe operations
        """
        self.config = config or CompositionConfig()
        self.template = template
        self.ffmpeg = ffmpeg_wrapper or get_ffmpeg_wrapper()

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

    async def compose_scenes(
        self,
        scenes: list["Scene"],
        scene_tts_results: list["SceneTTSResult"],
        scene_visuals: list["SceneVisualResult"],
        combined_audio_path: Path,
        subtitle_file: Path | None,
        output_path: Path,
        persona_style: "PersonaStyleConfig | None" = None,
        background_music_path: Path | None = None,
        title_text: str | None = None,
        headline_keyword: str | None = None,
        headline_hook: str | None = None,
    ) -> CompositionResult:
        """Compose video from scene-based components.

        This method handles scene-specific visual treatments:
        - NEUTRAL scenes: Standard visuals
        - PERSONA scenes: Accent color overlay, left border
        - EMPHASIS scenes: Background box effect

        Transitions between scenes are applied based on SceneType transitions
        (e.g., FLASH for fact→opinion).

        Korean Shorts Standard Layout:
        ┌──────────────────┐
        │  headline_keyword │  ← Line 1 (accent color)
        │  headline_hook    │  ← Line 2 (white)
        ├──────────────────┤
        │   visual content  │
        ├──────────────────┤
        │     subtitles     │
        └──────────────────┘

        Args:
            scenes: List of Scene objects with metadata
            scene_tts_results: List of SceneTTSResult with timing
            scene_visuals: List of SceneVisualResult with assets
            combined_audio_path: Path to concatenated audio file
            subtitle_file: Path to subtitle file (ASS format)
            output_path: Output video path
            persona_style: PersonaStyleConfig for visual styling
            background_music_path: Optional background music
            headline_keyword: Line 1 of headline (keyword, colored)
            headline_hook: Line 2 of headline (hook/description, white)

        Returns:
            CompositionResult with final video info
        """
        output_path = output_path.with_suffix(".mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="bsforge_scene_") as temp_dir:
            temp_path = Path(temp_dir)

            logger.info(f"Composing scene-based video: {len(scenes)} scenes")

            # Step 1: Create video segment for each scene
            scene_segments: list[Path] = []

            for i, (scene, tts_result, visual_result) in enumerate(
                zip(scenes, scene_tts_results, scene_visuals, strict=False)
            ):
                visual_style = scene.inferred_visual_style
                duration = tts_result.duration_seconds

                logger.debug(
                    f"Processing scene {i}: type={scene.scene_type.value}, "
                    f"style={visual_style.value}, duration={duration:.2f}s"
                )

                # Create segment with style-appropriate effects
                segment_path = await self._create_scene_segment(
                    asset=visual_result.asset,
                    duration=duration,
                    segment_index=i,
                    visual_style=visual_style,
                    persona_style=persona_style,
                    temp_dir=temp_path,
                )

                scene_segments.append(segment_path)

            # Step 2: Apply transitions between scenes
            video_sequence = await self._concat_scenes_with_transitions(
                segments=scene_segments,
                scenes=scenes,
                temp_dir=temp_path,
            )

            # Step 3: Add combined audio
            with_audio = temp_path / "with_audio.mp4"
            await self._add_audio_file(
                video_path=video_sequence,
                audio_path=combined_audio_path,
                output_path=with_audio,
            )

            # Step 4: Add background music if provided
            if background_music_path and background_music_path.exists():
                with_music = temp_path / "with_music.mp4"
                await self._add_background_music(
                    video_path=with_audio,
                    music_path=background_music_path,
                    output_path=with_music,
                )
                with_audio = with_music

            # Step 5: Add headline overlay (Korean shorts style - 2 lines)
            if headline_keyword and headline_hook and self._should_add_headline():
                with_headline = temp_path / "with_headline.mp4"
                await self._add_headline_overlay(
                    video_path=with_audio,
                    line1_text=headline_keyword,
                    line2_text=headline_hook,
                    output_path=with_headline,
                )
                with_audio = with_headline
                logger.info(f"Added headline: '{headline_keyword}' / '{headline_hook}'")

            # Step 6: Burn subtitles
            if subtitle_file and subtitle_file.exists():
                await self._burn_subtitles(
                    video_path=with_audio,
                    subtitle_path=subtitle_file,
                    output_path=output_path,
                )
            else:
                shutil.copy(with_audio, output_path)

        # Get final video info
        duration = await self._get_video_duration(output_path)
        file_size = output_path.stat().st_size

        logger.info(
            f"Scene composition complete: {output_path}, "
            f"duration={duration:.2f}s, size={file_size / 1024 / 1024:.1f}MB"
        )

        return CompositionResult(
            video_path=output_path,
            duration_seconds=duration,
            file_size_bytes=file_size,
            resolution=f"{self.config.width}x{self.config.height}",
            fps=self.config.fps,
        )

    async def _create_scene_segment(
        self,
        asset: VisualAsset,
        duration: float,
        segment_index: int,
        visual_style: "VisualStyle",
        persona_style: "PersonaStyleConfig | None",
        temp_dir: Path,
    ) -> Path:
        """Create a video segment with style-appropriate effects.

        Args:
            asset: Visual asset for this scene
            duration: Segment duration
            segment_index: Segment index
            visual_style: Visual style (NEUTRAL, PERSONA, EMPHASIS)
            persona_style: PersonaStyleConfig for persona scenes
            temp_dir: Temp directory

        Returns:
            Path to video segment
        """
        if not asset.path:
            raise ValueError("Asset has no local path")

        logger.info(
            f"Creating segment {segment_index}: asset.path={asset.path}, "
            f"source_id={asset.source_id}, exists={asset.path.exists() if asset.path else False}"
        )

        output_path = temp_dir / f"scene_segment_{segment_index}.mp4"

        # Build style-specific filter
        vf = self._build_style_filter(
            duration=duration,
            segment_index=segment_index,
            visual_style=visual_style,
            persona_style=persona_style,
        )

        if asset.is_video:
            # Video asset
            stream = self.ffmpeg.video_with_filters(
                input_path=asset.path,
                output_path=output_path,
                vf=vf,
                duration=duration,
                fps=self.config.fps,
                crf=self.config.crf,
                preset=self.config.preset,
                no_audio=True,
            )
        else:
            # Image asset - loop and apply Ken Burns
            stream = self.ffmpeg.image_to_video_with_filters(
                image_path=asset.path,
                output_path=output_path,
                duration=duration,
                vf=vf,
                fps=self.config.fps,
                crf=self.config.crf,
                preset=self.config.preset,
            )

        await self.ffmpeg.run(stream)
        return output_path

    def _build_style_filter(
        self,
        duration: float,
        segment_index: int,
        visual_style: "VisualStyle",
        persona_style: "PersonaStyleConfig | None",
    ) -> str:
        """Build FFmpeg filter based on visual style.

        Args:
            duration: Segment duration
            segment_index: Index for alternating effects
            visual_style: Visual style enum
            persona_style: PersonaStyleConfig for colors

        Returns:
            FFmpeg filter string
        """
        from app.models.scene import VisualStyle

        w = self.config.width
        h = self.config.height
        fps = self.config.fps
        total_frames = int(duration * fps)

        # Get colors from persona style or defaults
        if persona_style:
            accent_color = persona_style.accent_color.lstrip("#")
            overlay_opacity = (
                persona_style.overlay_opacity_persona
                if visual_style == VisualStyle.PERSONA
                else persona_style.overlay_opacity_neutral
            )
            border_width = persona_style.border_width if persona_style.use_persona_border else 0
        else:
            accent_color = "FF6B6B"
            overlay_opacity = 0.3
            border_width = 4

        # Base scale and Ken Burns
        zoom_speed = 0.0005
        if segment_index % 2 == 0:
            zoom_expr = f"zoom+{zoom_speed}"
        else:
            zoom_expr = f"if(eq(on,1),1.15,zoom-{zoom_speed})"

        # Scale to 2x output resolution for zoompan headroom (safer than 8000)
        scale_w = w * 2
        scale_h = h * 2

        base_filter = (
            f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={scale_w}:{scale_h},"
            f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total_frames}:s={w}x{h}:fps={fps},"
            f"setsar=1"
        )

        # Add overlay based on style
        if visual_style == VisualStyle.NEUTRAL:
            # Standard overlay (30% darken)
            overlay_filter = f",colorchannelmixer=aa={1 - overlay_opacity}"

        elif visual_style == VisualStyle.PERSONA:
            # Persona style: accent color tint + left border
            # Convert accent hex to RGB
            ar = int(accent_color[0:2], 16) / 255
            ag = int(accent_color[2:4], 16) / 255
            ab = int(accent_color[4:6], 16) / 255

            # Subtle color tint toward accent
            tint_strength = 0.1
            overlay_filter = (
                f",colorchannelmixer="
                f"rr={1 - tint_strength}:rg=0:rb=0:ra=0:"
                f"gr=0:gg={1 - tint_strength}:gb=0:ga=0:"
                f"br=0:bg=0:bb={1 - tint_strength}:ba=0:"
                f"ar={ar * tint_strength}:ag={ag * tint_strength}:ab={ab * tint_strength}:aa=1"
            )

            # Add left border for persona scenes
            if border_width > 0:
                overlay_filter += (
                    f",drawbox=x=0:y=0:w={border_width}:h={h}:" f"color=0x{accent_color}:t=fill"
                )

        elif visual_style == VisualStyle.EMPHASIS:
            # Emphasis style: darker overlay, slight vignette
            overlay_filter = f",colorchannelmixer=aa={1 - overlay_opacity - 0.1}," f"vignette=PI/4"

        else:
            overlay_filter = ""

        return base_filter + overlay_filter

    async def _concat_scenes_with_transitions(
        self,
        segments: list[Path],
        scenes: list["Scene"],
        temp_dir: Path,
    ) -> Path:
        """Concatenate scene segments with appropriate transitions.

        Args:
            segments: List of segment paths
            scenes: List of Scene objects (for transition info)
            temp_dir: Temp directory

        Returns:
            Path to concatenated video
        """
        from app.models.scene import TransitionType

        if len(segments) == 1:
            return segments[0]

        # NOTE: FFmpeg xfade requires exact segment durations.
        # Current implementation uses simple concat with fade-in at start.
        # For proper crossfade transitions:
        # 1. Pass segment durations alongside segment paths
        # 2. Build ffmpeg filter chain: xfade=transition=fade:duration=0.5:offset=<duration-0.5>
        # 3. Chain multiple xfade filters for multiple segments
        # This is deferred as it requires structural changes to pass duration info.

        # Get recommended transitions from scenes
        transitions: list[TransitionType] = []
        for i in range(len(scenes) - 1):
            current = scenes[i]
            # Use scene's transition_out setting
            transitions.append(current.transition_out)

        # Check if any transitions need special handling (FLASH)
        has_flash = any(t == TransitionType.FLASH for t in transitions)

        # Create concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment}'\n")

        output_path = temp_dir / "sequence.mp4"

        if not has_flash:
            # Simple concat without special effects
            stream = self.ffmpeg.concat_with_file(
                concat_file_path=concat_file,
                output_path=output_path,
                copy_codec=True,
            )
            await self.ffmpeg.run(stream)
            return output_path

        # With transitions: re-encode with fade effects
        # Use concat then apply fade filter
        temp_concat = temp_dir / "temp_concat.mp4"
        concat_stream = self.ffmpeg.concat_with_file(
            concat_file_path=concat_file,
            output_path=temp_concat,
            copy_codec=True,
        )
        await self.ffmpeg.run(concat_stream)

        # Apply fade in at start for visual polish
        fade_stream = self.ffmpeg.video_with_filters(
            input_path=temp_concat,
            output_path=output_path,
            vf="fade=t=in:st=0:d=0.1",
            fps=self.config.fps,
            crf=self.config.crf,
            preset=self.config.preset,
        )
        await self.ffmpeg.run(fade_stream)
        return output_path

    async def _add_audio_file(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> None:
        """Add audio file to video.

        Args:
            video_path: Input video path
            audio_path: Audio file path
            output_path: Output path
        """
        stream = self.ffmpeg.add_audio_to_video(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            audio_codec=self.config.audio_codec,
            audio_bitrate=self.config.audio_bitrate,
            shortest=True,
        )
        await self.ffmpeg.run(stream)

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

        stream = self.ffmpeg.video_with_filters(
            input_path=asset.path,
            output_path=output_path,
            vf=scale_filter,
            duration=max_duration,
            fps=self.config.fps,
            crf=self.config.crf,
            preset=self.config.preset,
            no_audio=True,
        )

        await self.ffmpeg.run(stream)
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
        enable_ken_burns: bool = True,
    ) -> Path:
        """Convert image to video segment with Ken Burns effect.

        Ken Burns effect is enabled based on template settings.
        If frame layout is enabled, image is placed in a centered frame.

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

        # Check if frame layout should be used
        if self._should_use_frame_layout():
            # Use filter_complex for frame layout
            vf = self._build_frame_layout_filter(duration, segment_index)
            stream = self.ffmpeg.image_to_video_with_filters(
                image_path=asset.path,
                output_path=output_path,
                duration=duration,
                vf=vf,
                fps=self.config.fps,
                crf=self.config.crf,
                preset=self.config.preset,
            )
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

            stream = self.ffmpeg.image_to_video_with_filters(
                image_path=asset.path,
                output_path=output_path,
                duration=duration,
                vf=vf,
                fps=self.config.fps,
                crf=self.config.crf,
                preset=self.config.preset,
            )

        await self.ffmpeg.run(stream)
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
        if not self.template or not self.template.layout:
            raise RuntimeError("Template with layout required for frame filter")
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

        # Scale to 2x content size for zoompan headroom (safer than 8000)
        scale_w = content_w * 2
        scale_h = content_h * 2

        # Scale image and apply Ken Burns to content size
        image_filter = (
            f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={scale_w}:{scale_h},"
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
            pad_w = content_w + border_w * 2
            pad_h = content_h + border_w * 2
            image_filter += f",pad={pad_w}:{pad_h}:{border_w}:{border_w}:color=#{border_color}"
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

        stream = self.ffmpeg.image_to_video_with_filters(
            image_path=asset.path,
            output_path=output_path,
            duration=duration,
            vf=vf,
            fps=self.config.fps,
            crf=self.config.crf,
            preset=self.config.preset,
        )

        await self.ffmpeg.run(stream)
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
            # Default values when no template
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

        # Scale to 2x output resolution for zoompan headroom (safer than 8000)
        # This provides enough room for Ken Burns effect without memory issues
        scale_w = w * 2
        scale_h = h * 2

        # Scale up first (to allow room for zooming), then apply zoompan
        base_filter = (
            f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={scale_w}:{scale_h},"
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

        lavfi_source = f"color=c=black:s={self.config.width}x{self.config.height}"
        stream = self.ffmpeg.create_lavfi_video(
            lavfi_source=lavfi_source,
            output_path=output_path,
            duration=duration,
            fps=self.config.fps,
        )

        await self.ffmpeg.run(stream)
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

        # Create concat file
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment}'\n")

        output_path = temp_dir / "sequence.mp4"

        if not add_flash:
            # Simple concat without transitions
            stream = self.ffmpeg.concat_with_file(
                concat_file_path=concat_file,
                output_path=output_path,
                copy_codec=True,
            )
            await self.ffmpeg.run(stream)
            return output_path

        # Concat with flash transitions
        # Use concat demuxer then apply fade filter
        temp_concat = temp_dir / "temp_concat.mp4"
        concat_stream = self.ffmpeg.concat_with_file(
            concat_file_path=concat_file,
            output_path=temp_concat,
            copy_codec=True,
        )
        await self.ffmpeg.run(concat_stream)

        # Add fade in at start for visual polish
        fade_stream = self.ffmpeg.video_with_filters(
            input_path=temp_concat,
            output_path=output_path,
            vf="fade=t=in:st=0:d=0.1",
            fps=self.config.fps,
            crf=self.config.crf,
            preset=self.config.preset,
        )
        await self.ffmpeg.run(fade_stream)
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
        stream = self.ffmpeg.add_audio_to_video(
            video_path=video_path,
            audio_path=audio_path,
            output_path=output_path,
            audio_codec=self.config.audio_codec,
            audio_bitrate=self.config.audio_bitrate,
            shortest=True,
        )
        await self.ffmpeg.run(stream)

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
        stream = self.ffmpeg.mix_background_audio(
            video_path=video_path,
            bg_audio_path=music_path,
            output_path=output_path,
            bg_volume=self.config.background_music_volume,
            audio_codec=self.config.audio_codec,
            audio_bitrate=self.config.audio_bitrate,
        )
        await self.ffmpeg.run(stream)

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
        stream = self.ffmpeg.burn_ass_subtitles(
            video_path=video_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            crf=self.config.crf,
            preset=self.config.preset,
        )
        await self.ffmpeg.run(stream)

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
            color_grade = (
                ",eq=brightness=0.05:contrast=1.1:saturation=1.2"
                ",colorbalance=rs=0.1:gs=0.05:bs=-0.1"
            )
            return base_filter + color_grade

        return base_filter

    async def _get_video_duration(self, video_path: Path) -> float:
        """Get video duration.

        Args:
            video_path: Path to video file

        Returns:
            Duration in seconds

        Raises:
            FFmpegError: If probing fails
        """
        return await self.ffmpeg.get_duration(video_path)

    def _should_add_headline(self) -> bool:
        """Check if 2-line headline should be added based on template.

        Returns:
            True if headline is enabled in template
        """
        if not self.template or not self.template.layout:
            return False

        headline_config = self.template.layout.headline
        return headline_config is not None and headline_config.enabled

    async def _add_headline_overlay(
        self,
        video_path: Path,
        line1_text: str,
        line2_text: str,
        output_path: Path,
    ) -> None:
        """Add 2-line headline overlay to video (Korean shorts style).

        Creates headline with:
        - Optional black background area at top
        - Line 1: Keyword in accent color
        - Line 2: Description in white

        Layout:
        ┌──────────────────┐
        │███ 검은 배경 ████│
        │   키워드 (핑크)   │
        │   설명 (흰색)     │
        └──────────────────┘

        Args:
            video_path: Input video path
            line1_text: First line (keyword, colored)
            line2_text: Second line (description, white)
            output_path: Output path
        """
        if not self.template or not self.template.layout:
            return

        headline_config = self.template.layout.headline
        if not headline_config:
            return

        # Get settings from template
        font_path = find_font_by_name(headline_config.font_name)
        outline_color = headline_config.outline_color.lstrip("#")

        # Line 1 settings (keyword with accent color)
        line1_size = headline_config.line1.font_size
        line1_color = headline_config.line1.color.lstrip("#")
        line1_outline = headline_config.line1.outline_width

        # Line 2 settings (description in white)
        line2_size = headline_config.line2.font_size
        line2_color = headline_config.line2.color.lstrip("#")
        line2_outline = headline_config.line2.outline_width

        # Escape special characters for FFmpeg
        def escape_text(text: str) -> str:
            return (
                text.replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace(":", "\\:")
                .replace("%", "\\%")
            )

        escaped_line1 = escape_text(line1_text)
        escaped_line2 = escape_text(line2_text)

        # Build filter chain
        filter_parts = []

        # Add black background if enabled
        if headline_config.background_enabled:
            bg_height = int(self.config.height * headline_config.background_height_ratio)
            bg_color = headline_config.background_color.lstrip("#")
            bg_opacity = headline_config.background_opacity

            # Draw black rectangle at top
            filter_parts.append(
                f"drawbox=x=0:y=0:w={self.config.width}:h={bg_height}:"
                f"color=0x{bg_color}@{bg_opacity}:t=fill"
            )

            # Position text within the black area (vertically centered)
            line_spacing = headline_config.line_spacing
            total_text_height = line1_size + int(line2_size * line_spacing)
            position_y = (bg_height - total_text_height) // 2 + 20  # Slight offset for balance
            line2_y = position_y + int(line1_size * line_spacing)
        else:
            # Position from config ratio
            position_y = int(self.config.height * headline_config.position_y_ratio)
            line_spacing = headline_config.line_spacing
            line2_y = position_y + int(line1_size * line_spacing)

        # Build shadow filter (if enabled and no background)
        if headline_config.shadow_enabled and not headline_config.background_enabled:
            shadow_offset = headline_config.shadow_offset
            shadow_color = headline_config.shadow_color.lstrip("#")
            filter_parts.extend(
                [
                    f"drawtext=text='{escaped_line1}':"
                    f"fontfile={font_path}:"
                    f"fontsize={line1_size}:"
                    f"fontcolor={shadow_color}@0.7:"
                    f"x=(w-text_w)/2+{shadow_offset}:"
                    f"y={position_y}+{shadow_offset}",
                    f"drawtext=text='{escaped_line2}':"
                    f"fontfile={font_path}:"
                    f"fontsize={line2_size}:"
                    f"fontcolor={shadow_color}@0.7:"
                    f"x=(w-text_w)/2+{shadow_offset}:"
                    f"y={line2_y}+{shadow_offset}",
                ]
            )

        # Add main text (Line 1 - keyword, accent color)
        filter_parts.append(
            f"drawtext=text='{escaped_line1}':"
            f"fontfile={font_path}:"
            f"fontsize={line1_size}:"
            f"fontcolor={line1_color}:"
            f"borderw={line1_outline}:"
            f"bordercolor={outline_color}:"
            f"x=(w-text_w)/2:"
            f"y={position_y}"
        )

        # Add main text (Line 2 - description, white)
        filter_parts.append(
            f"drawtext=text='{escaped_line2}':"
            f"fontfile={font_path}:"
            f"fontsize={line2_size}:"
            f"fontcolor={line2_color}:"
            f"borderw={line2_outline}:"
            f"bordercolor={outline_color}:"
            f"x=(w-text_w)/2:"
            f"y={line2_y}"
        )

        # Join all filter parts
        drawtext_filter = ",".join(filter_parts)

        stream = self.ffmpeg.video_with_drawtext(
            video_path=video_path,
            output_path=output_path,
            drawtext_filter=drawtext_filter,
            crf=self.config.crf,
            preset=self.config.preset,
        )
        await self.ffmpeg.run(stream)
        logger.debug(f"Added headline overlay: '{line1_text}' / '{line2_text}'")


__all__ = ["FFmpegCompositor", "CompositionResult"]
