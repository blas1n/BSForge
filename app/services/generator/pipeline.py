"""Video generation pipeline.

Orchestrates the complete video generation process from script to final video.
"""

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config.video import VideoGenerationConfig
from app.models.script import Script
from app.models.video import Video, VideoStatus
from app.services.generator.compositor import FFmpegCompositor
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.thumbnail import ThumbnailGenerator
from app.services.generator.tts.base import TTSConfig
from app.services.generator.tts.factory import TTSEngineFactory
from app.services.generator.visual.manager import VisualSourcingManager

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
    6. Generate thumbnail
    7. Save video record to database

    Example:
        >>> pipeline = VideoGenerationPipeline(
        ...     tts_factory=tts_factory,
        ...     visual_manager=visual_manager,
        ...     subtitle_generator=subtitle_gen,
        ...     compositor=compositor,
        ...     thumbnail_generator=thumbnail_gen,
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
        thumbnail_generator: ThumbnailGenerator,
        db_session_factory: Any,
        config: VideoGenerationConfig | None = None,
    ) -> None:
        """Initialize VideoGenerationPipeline.

        Args:
            tts_factory: TTS engine factory
            visual_manager: Visual sourcing manager
            subtitle_generator: Subtitle generator
            compositor: FFmpeg compositor
            thumbnail_generator: Thumbnail generator
            db_session_factory: Database session factory
            config: Video generation configuration
        """
        self.tts_factory = tts_factory
        self.visual_manager = visual_manager
        self.subtitle_generator = subtitle_generator
        self.compositor = compositor
        self.thumbnail_generator = thumbnail_generator
        self.db_session_factory = db_session_factory
        self.config = config or VideoGenerationConfig()

    async def generate(
        self,
        script: Script,
        voice_id: str | None = None,
        tts_provider: str | None = None,
    ) -> VideoGenerationResult:
        """Generate video from script.

        Args:
            script: Script model instance
            voice_id: Optional TTS voice override
            tts_provider: Optional TTS provider override

        Returns:
            VideoGenerationResult with file paths and metadata

        Raises:
            ValueError: If script is invalid
            RuntimeError: If generation fails
        """
        start_time = time.time()

        # Validate script
        if not script.script_text:
            raise ValueError("Script has no text content")

        # Determine output directory
        output_dir = Path(self.config.output_dir) / str(script.channel_id) / str(script.id)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create temp directory
        temp_dir = Path(self.config.temp_dir) / str(script.id)
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Starting video generation for script {script.id}")

            # Step 1: Get TTS engine and voice
            provider = tts_provider or self.config.tts.provider
            engine = self.tts_factory.get_engine(provider)

            # Determine voice from persona or config
            final_voice_id = voice_id or self._get_voice_for_script(script)

            # Step 2: Generate audio with TTS
            logger.info(f"Generating audio with {provider}, voice={final_voice_id}")

            tts_config = TTSConfig(
                voice_id=final_voice_id,
                speed=self.config.tts.speed,
                pitch=self.config.tts.pitch,
                volume=self.config.tts.volume,
            )

            tts_result = await engine.synthesize(
                text=script.script_text,
                config=tts_config,
                output_path=output_dir / "audio",
            )

            logger.info(f"Audio generated: {tts_result.duration_seconds:.1f}s")

            # Step 3: Generate subtitles
            subtitle_path = None
            if self.config.subtitle.enabled:
                logger.info("Generating subtitles")

                if tts_result.word_timestamps:
                    subtitle_file = self.subtitle_generator.generate_from_timestamps(
                        tts_result.word_timestamps
                    )
                else:
                    subtitle_file = self.subtitle_generator.generate_from_script(
                        script.script_text,
                        tts_result.duration_seconds,
                    )

                if self.config.subtitle.format == "ass":
                    subtitle_path = self.subtitle_generator.to_ass(
                        subtitle_file,
                        output_dir / "subtitle",
                    )
                else:
                    subtitle_path = self.subtitle_generator.to_srt(
                        subtitle_file,
                        output_dir / "subtitle",
                    )

                logger.info(f"Subtitles generated: {len(subtitle_file.segments)} segments")

            # Step 4: Source visuals
            logger.info("Sourcing visual assets")

            keywords = self._extract_keywords(script)

            visuals = await self.visual_manager.source_visuals(
                keywords=keywords,
                duration_needed=tts_result.duration_seconds,
                output_dir=temp_dir / "visuals",
            )

            visual_sources = list({v.source or "unknown" for v in visuals})
            logger.info(f"Sourced {len(visuals)} visual assets from: {visual_sources}")

            # Step 5: Compose video
            logger.info("Composing video")

            composition_result = await self.compositor.compose(
                audio=tts_result,
                visuals=visuals,
                subtitle_file=subtitle_path,
                output_path=output_dir / "video",
            )

            logger.info(f"Video composed: {composition_result.duration_seconds:.1f}s")

            # Step 6: Generate thumbnail
            logger.info("Generating thumbnail")

            # Use first visual or fallback
            thumbnail_background = visuals[0] if visuals else None
            title = self._get_thumbnail_title(script)

            thumbnail_path = await self.thumbnail_generator.generate(
                title=title,
                output_path=output_dir / "thumbnail",
                background=thumbnail_background,
            )

            logger.info(f"Thumbnail generated: {thumbnail_path}")

            # Calculate generation time
            generation_time = int(time.time() - start_time)

            result = VideoGenerationResult(
                video_path=composition_result.video_path,
                thumbnail_path=thumbnail_path,
                audio_path=tts_result.audio_path,
                subtitle_path=subtitle_path,
                duration_seconds=composition_result.duration_seconds,
                file_size_bytes=composition_result.file_size_bytes,
                tts_service=provider,
                tts_voice_id=final_voice_id,
                visual_sources=visual_sources,
                generation_time_seconds=generation_time,
            )

            logger.info(
                f"Video generation complete: {result.video_path}, "
                f"duration={result.duration_seconds:.1f}s, "
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

    async def generate_and_save(
        self,
        script: Script,
        voice_id: str | None = None,
        tts_provider: str | None = None,
    ) -> Video:
        """Generate video and save to database.

        Args:
            script: Script model instance
            voice_id: Optional TTS voice override
            tts_provider: Optional TTS provider override

        Returns:
            Video model instance
        """
        # Generate video
        result = await self.generate(
            script=script,
            voice_id=voice_id,
            tts_provider=tts_provider,
        )

        # Create Video model
        video = Video(
            id=uuid.uuid4(),
            channel_id=script.channel_id,
            script_id=script.id,
            video_path=str(result.video_path),
            thumbnail_path=str(result.thumbnail_path),
            audio_path=str(result.audio_path),
            subtitle_path=str(result.subtitle_path) if result.subtitle_path else None,
            duration_seconds=result.duration_seconds,
            file_size_bytes=result.file_size_bytes,
            resolution=f"{self.config.composition.width}x{self.config.composition.height}",
            fps=self.config.composition.fps,
            tts_service=result.tts_service,
            tts_voice_id=result.tts_voice_id,
            visual_sources=result.visual_sources,
            generation_time_seconds=result.generation_time_seconds,
            generation_metadata={
                "config": {
                    "tts_speed": self.config.tts.speed,
                    "subtitle_enabled": self.config.subtitle.enabled,
                    "composition_crf": self.config.composition.crf,
                },
            },
            status=VideoStatus.GENERATED,
        )

        # Save to database
        async with self.db_session_factory() as session:
            session.add(video)
            await session.commit()
            await session.refresh(video)

        logger.info(f"Video saved to database: {video.id}")
        return video

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

    def _extract_keywords(self, script: Script) -> list[str]:
        """Extract keywords for visual search.

        Args:
            script: Script model

        Returns:
            List of keywords
        """
        keywords: list[str] = []

        # From topic if available
        if hasattr(script, "topic") and script.topic:
            if hasattr(script.topic, "keywords") and script.topic.keywords:
                keywords.extend(script.topic.keywords[:5])
            if hasattr(script.topic, "title") and script.topic.title:
                # Extract words from title
                title_words = script.topic.title.split()[:3]
                keywords.extend(title_words)

        # Fallback: extract from script text
        if not keywords:
            words = script.script_text.split()[:10]
            keywords = [w for w in words if len(w) > 3][:5]

        return keywords or ["abstract", "background"]

    def _get_thumbnail_title(self, script: Script) -> str:
        """Get title for thumbnail.

        Args:
            script: Script model

        Returns:
            Title string
        """
        # Try topic title first
        if (
            hasattr(script, "topic")
            and script.topic
            and hasattr(script.topic, "title")
            and script.topic.title
        ):
            return str(script.topic.title)

        # Fallback: first line of script
        first_line = script.script_text.split("\n")[0][:50]
        return first_line if first_line else "Video"


__all__ = [
    "VideoGenerationPipeline",
    "VideoGenerationResult",
]
