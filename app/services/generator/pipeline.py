"""Video generation pipeline.

Orchestrates the complete video generation process from script to final video.
Supports template-based styling for consistent visual appearance.
Supports scene-based generation for BSForge's scene architecture.
"""

import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.video import VideoGenerationConfig
from app.config.video_template import VideoTemplateConfig
from app.core.template_loader import VideoTemplateLoader
from app.core.types import SessionFactory
from app.models.script import Script
from app.services.generator.bgm import BGMManager
from app.services.generator.compositor import FFmpegCompositor
from app.services.generator.ffmpeg import FFmpegWrapper
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.tts.base import TTSSynthesisConfig
from app.services.generator.tts.factory import TTSEngineFactory
from app.services.generator.tts.utils import concatenate_scene_audio
from app.services.generator.visual.manager import VisualSourcingManager

if TYPE_CHECKING:
    from app.config.persona import PersonaStyleConfig
    from app.models.scene import SceneScript

logger = logging.getLogger(__name__)


@dataclass
class VideoGenerationResult:
    """Result of video generation.

    Attributes:
        video_path: Path to final video file
        thumbnail_path: Path to thumbnail image
        audio_path: Path to audio file
        subtitle_path: Path to subtitle file
        duration_seconds: Video duration
        file_size_bytes: Video file size
        tts_service: TTS service used
        tts_voice_id: TTS voice used
        visual_sources: List of visual source types used
        generation_time_seconds: Time taken to generate
        generated_at: Generation timestamp
    """

    video_path: Path
    thumbnail_path: Path
    audio_path: Path
    subtitle_path: Path | None
    duration_seconds: float
    file_size_bytes: int
    tts_service: str
    tts_voice_id: str
    visual_sources: list[str]
    generation_time_seconds: int
    generated_at: datetime = field(default_factory=datetime.utcnow)


class VideoGenerationPipeline:
    """Orchestrate complete video generation.

    Pipeline steps:
    1. Load script from database
    2. Generate audio with TTS
    3. Generate subtitles from word timestamps
    4. Source visual assets
    5. Compose video with FFmpeg
    6. Extract thumbnail from first frame
    7. Save video record to database

    Example:
        >>> pipeline = VideoGenerationPipeline(
        ...     tts_factory=tts_factory,
        ...     visual_manager=visual_manager,
        ...     subtitle_generator=subtitle_gen,
        ...     compositor=compositor,
        ...     db_session_factory=session_factory,
        ... )
        >>> result = await pipeline.generate(script_id, channel_id)
    """

    def __init__(
        self,
        tts_factory: TTSEngineFactory,
        visual_manager: VisualSourcingManager,
        subtitle_generator: SubtitleGenerator,
        compositor: FFmpegCompositor,
        ffmpeg_wrapper: FFmpegWrapper,
        db_session_factory: SessionFactory,
        config: VideoGenerationConfig,
        template_loader: VideoTemplateLoader,
        bgm_manager: BGMManager,
    ) -> None:
        """Initialize VideoGenerationPipeline.

        Args:
            tts_factory: TTS engine factory
            visual_manager: Visual sourcing manager
            subtitle_generator: Subtitle generator
            compositor: FFmpeg compositor
            ffmpeg_wrapper: FFmpeg wrapper for type-safe operations
            db_session_factory: Database session factory
            config: Video generation configuration
            template_loader: Video template loader
            bgm_manager: BGM manager for background music
        """
        self.tts_factory = tts_factory
        self.visual_manager = visual_manager
        self.subtitle_generator = subtitle_generator
        self.compositor = compositor
        self.ffmpeg = ffmpeg_wrapper
        self.db_session_factory = db_session_factory
        self.config = config
        self.template_loader = template_loader
        self.bgm_manager = bgm_manager

    async def generate(
        self,
        script: Script,
        scene_script: "SceneScript",
        voice_id: str | None = None,
        tts_provider: str | None = None,
        template_name: str | None = None,
        persona_style: "PersonaStyleConfig | None" = None,
    ) -> VideoGenerationResult:
        """Generate video from scene-based script.

        This method uses the scene-based generation flow:
        1. Per-scene TTS generation
        2. Audio concatenation
        3. Scene-aware subtitles
        4. Per-scene visual sourcing
        5. Scene-based composition with transitions
        6. Thumbnail generation

        Args:
            script: Script model instance
            scene_script: SceneScript with list of Scene objects
            voice_id: Optional TTS voice override
            tts_provider: Optional TTS provider override
            template_name: Video template name
            persona_style: PersonaStyleConfig for visual styling

        Returns:
            VideoGenerationResult with file paths and metadata
        """
        start_time = time.time()

        if not scene_script.scenes:
            raise ValueError("SceneScript has no scenes")

        # Load template if specified
        template: VideoTemplateConfig | None = None
        if template_name:
            try:
                template = self.template_loader.load(template_name)
                logger.info(f"Using video template: {template_name}")
            except Exception as e:
                logger.warning(f"Failed to load template '{template_name}': {e}")

        # Update compositor with template
        if template:
            self.compositor.template = template

        # Determine output directory (simplified to single UUID)
        output_dir = Path(self.config.output_dir) / str(script.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create temp directory
        temp_dir = Path(self.config.temp_dir) / str(script.id)
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(
                f"Starting scene-based video generation for script {script.id}, "
                f"{len(scene_script.scenes)} scenes"
            )

            # Step 1: Get TTS engine
            provider = tts_provider or self.config.tts.provider
            engine = self.tts_factory.get_engine(provider)
            final_voice_id = voice_id or self._get_voice_for_script(script)

            tts_config = TTSSynthesisConfig(
                voice_id=final_voice_id,
                speed=self.config.tts.speed,
                pitch=self.config.tts.pitch,
                volume=self.config.tts.volume,
            )

            # Step 2: Per-scene TTS generation
            logger.info(f"Generating audio for {len(scene_script.scenes)} scenes")

            scene_tts_results = await engine.synthesize_scenes(
                scenes=scene_script.scenes,
                config=tts_config,
                output_dir=temp_dir / "audio_scenes",
            )

            total_duration = sum(r.duration_seconds for r in scene_tts_results)
            logger.info(f"Scene audio generated: {total_duration:.1f}s total")

            # Step 3: Concatenate audio
            logger.info("Concatenating scene audio")

            combined_tts = await concatenate_scene_audio(
                scene_results=scene_tts_results,
                output_path=output_dir / "audio",
                ffmpeg_wrapper=self.ffmpeg,
            )

            logger.info(f"Combined audio: {combined_tts.duration_seconds:.1f}s")

            # Step 4: Generate scene-aware subtitles
            subtitle_path = None
            if self.config.subtitle.enabled:
                logger.info("Generating scene-aware subtitles")

                subtitle_file = self.subtitle_generator.generate_from_scene_results(
                    scene_results=scene_tts_results,
                    scenes=scene_script.scenes,
                    persona_style=persona_style,
                    template=template,
                )

                if self.config.subtitle.format == "ass":
                    subtitle_path = self.subtitle_generator.to_ass_with_scene_styles(
                        subtitle=subtitle_file,
                        output_path=output_dir / "subtitle",
                        scenes=scene_script.scenes,
                        scene_results=scene_tts_results,
                        persona_style=persona_style,
                        template=template,
                    )
                else:
                    subtitle_path = self.subtitle_generator.to_srt(
                        subtitle_file,
                        output_dir / "subtitle",
                    )

                logger.info(f"Subtitles generated: {len(subtitle_file.segments)} segments")

            # Step 5: Per-scene visual sourcing
            logger.info("Sourcing visuals for each scene")

            scene_visuals = await self.visual_manager.source_visuals_for_scenes(
                scenes=scene_script.scenes,
                scene_results=scene_tts_results,
                output_dir=temp_dir / "visuals",
            )

            visual_sources = list({v.asset.source or "unknown" for v in scene_visuals})
            logger.info(f"Sourced {len(scene_visuals)} scene visuals from: {visual_sources}")

            # Step 6: Scene-based composition
            logger.info("Composing scene-based video")

            # Get headline
            headline = scene_script.headline
            logger.info(f"Headline: '{headline}'")

            # Get BGM path if available
            background_music_path = None
            if self.bgm_manager and self.bgm_manager.is_enabled:
                background_music_path = await self.bgm_manager.get_bgm_for_video()
                if background_music_path:
                    logger.info(f"Using BGM: {background_music_path.name}")

            composition_result = await self.compositor.compose_scenes(
                scenes=scene_script.scenes,
                scene_tts_results=scene_tts_results,
                scene_visuals=scene_visuals,
                combined_audio_path=combined_tts.audio_path,
                subtitle_file=subtitle_path,
                output_path=output_dir / "video",
                background_music_path=background_music_path,
                persona_style=persona_style,
                headline=headline,
            )

            logger.info(f"Video composed: {composition_result.duration_seconds:.1f}s")

            # Step 7: Extract thumbnail from first frame
            logger.info("Extracting thumbnail from video")

            thumbnail_path = await self._extract_thumbnail(
                video_path=composition_result.video_path,
                output_path=output_dir / "thumbnail",
            )

            logger.info(f"Thumbnail extracted: {thumbnail_path}")

            # Calculate generation time
            generation_time = int(time.time() - start_time)

            result = VideoGenerationResult(
                video_path=composition_result.video_path,
                thumbnail_path=thumbnail_path,
                audio_path=combined_tts.audio_path,
                subtitle_path=subtitle_path,
                duration_seconds=composition_result.duration_seconds,
                file_size_bytes=composition_result.file_size_bytes,
                tts_service=provider,
                tts_voice_id=final_voice_id,
                visual_sources=visual_sources,
                generation_time_seconds=generation_time,
            )

            logger.info(
                f"Scene-based video generation complete: {result.video_path}, "
                f"duration={result.duration_seconds:.1f}s, "
                f"scenes={len(scene_script.scenes)}, "
                f"time={generation_time}s"
            )

            return result

        finally:
            # Cleanup temp directory
            if self.config.cleanup_temp and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dir: {e}")

    def _get_voice_for_script(self, script: Script) -> str:
        """Determine voice ID for script.

        Uses persona settings if available, otherwise config defaults.

        Args:
            script: Script model

        Returns:
            Voice ID string
        """
        # Try to get from channel's persona
        try:
            if hasattr(script, "channel") and script.channel:
                persona = script.channel.persona
                if persona and persona.voice_id:
                    return persona.voice_id
        except Exception:
            pass

        # Fallback to config defaults
        # Simple heuristic: use Korean if script contains Korean characters
        has_korean = any("\uac00" <= char <= "\ud7a3" for char in script.script_text)

        if has_korean:
            return self.config.tts.default_voice_ko_male
        return self.config.tts.default_voice_en

    async def _extract_thumbnail(self, video_path: Path, output_path: Path) -> Path:
        """Extract first frame from video as thumbnail.

        Args:
            video_path: Path to video file
            output_path: Output path for thumbnail (without extension)

        Returns:
            Path to generated thumbnail image
        """
        thumbnail_path = output_path.with_suffix(".jpg")

        stream = self.ffmpeg.extract_frame(
            video_path=video_path,
            output_path=thumbnail_path,
            seek_seconds=0.0,
            quality=2,
        )
        await self.ffmpeg.run(stream)

        return thumbnail_path


__all__ = [
    "VideoGenerationPipeline",
    "VideoGenerationResult",
]
