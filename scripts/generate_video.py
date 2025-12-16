#!/usr/bin/env python3
"""Scene-based video generation script.

This script generates a complete YouTube Shorts video using BSForge's
scene-based pipeline. Supports both basic and template-based generation.

Usage:
    # Basic generation (default scenes)
    /home/vscode/.local/bin/uv run python scripts/generate_video.py

    # With template
    /home/vscode/.local/bin/uv run python scripts/generate_video.py --template korean_shorts_standard

    # Custom output directory
    /home/vscode/.local/bin/uv run python scripts/generate_video.py --output ./my_output

Layout (korean_shorts_standard template):
+------------------+
|  AI 기술 (핑크)   |  <- Line 1: keyword (accent color)
|  미래가 바뀐다    |  <- Line 2: hook (white)
+------------------+
|                  |
|   메인 이미지     |  <- fullscreen visual
|                  |
+------------------+
|   하단 자막       |  <- bottom caption
+------------------+
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_sample_scenes() -> tuple[list, str, str]:
    """Create sample scenes for demonstration.

    Returns:
        Tuple of (scenes list, headline_keyword, headline_hook)
    """
    from app.models.scene import Scene, SceneType, VisualHintType

    headline_keyword = "AI 기술"
    headline_hook = "미래가 어떻게 바뀔까?"

    scenes = [
        Scene(
            scene_type=SceneType.HOOK,
            text="AI가 우리 일상을 완전히 바꾸고 있습니다",
            keyword="AI technology future",
            visual_hint=VisualHintType.STOCK_IMAGE,
            emphasis_words=["AI", "일상"],
            subtitle_segments=[
                "AI가 우리 일상을",
                "완전히 바꾸고 있습니다",
            ],
        ),
        Scene(
            scene_type=SceneType.CONTENT,
            text="2024년 기준 전 세계 기업의 70%가 AI를 도입했습니다",
            keyword="business AI adoption",
            visual_hint=VisualHintType.STOCK_IMAGE,
            emphasis_words=["70%"],
            subtitle_segments=[
                "2024년 기준",
                "전 세계 기업의",
                "70%가 AI를",
                "도입했습니다",
            ],
        ),
        Scene(
            scene_type=SceneType.COMMENTARY,  # ← AI 페르소나 의견 (BSForge 차별점)
            text="솔직히 이 속도면 5년 후엔 상상도 못할 세상이 올 것 같아요",
            keyword="futuristic technology innovation",
            visual_hint=VisualHintType.STOCK_IMAGE,
            emphasis_words=["5년"],
            subtitle_segments=[
                "솔직히 이 속도면",
                "5년 후엔",
                "상상도 못할 세상이",
                "올 것 같아요",
            ],
        ),
        Scene(
            scene_type=SceneType.REACTION,  # ← 짧은 리액션
            text="와, 진짜 대박 아닌가요?",
            keyword="surprised reaction",
            visual_hint=VisualHintType.SOLID_COLOR,
            emphasis_words=["대박"],
            subtitle_segments=["와, 진짜", "대박 아닌가요?"],
        ),
        Scene(
            scene_type=SceneType.CONCLUSION,
            text="여러분은 AI 시대 어떻게 준비하고 계신가요?",
            keyword="AI preparation",
            visual_hint=VisualHintType.STOCK_IMAGE,
            emphasis_words=["준비"],
            subtitle_segments=[
                "여러분은 AI 시대",
                "어떻게 준비하고 계신가요?",
            ],
        ),
        Scene(
            scene_type=SceneType.CTA,
            text="좋아요와 구독 부탁드려요!",
            keyword="subscribe like",
            visual_hint=VisualHintType.STOCK_IMAGE,
            emphasis_words=["좋아요", "구독"],
            subtitle_segments=["좋아요와 구독", "부탁드려요!"],
        ),
    ]

    return scenes, headline_keyword, headline_hook


async def generate_video(
    output_dir: Path,
    template_name: str | None = None,
) -> None:
    """Generate a complete video using scene-based pipeline.

    Args:
        output_dir: Output directory for generated files
        template_name: Optional video template name
    """
    from app.config.persona import PersonaStyleConfig
    from app.config.video import CompositionConfig, SubtitleConfig, VisualConfig
    from app.services.generator.compositor import FFmpegCompositor
    from app.services.generator.subtitle import SubtitleGenerator
    from app.services.generator.thumbnail import ThumbnailGenerator
    from app.services.generator.tts.base import TTSConfig
    from app.services.generator.tts.factory import TTSEngineFactory
    from app.services.generator.tts.utils import concatenate_scene_audio
    from app.services.generator.visual.manager import VisualSourcingManager

    logger.info("=" * 60)
    logger.info("BSForge Video Generation")
    logger.info("=" * 60)

    # Load template if specified
    template = None
    if template_name:
        try:
            from app.core.template_loader import load_template

            template = load_template(template_name)
            logger.info(f"Template: {template.name}")
            if template.layout.headline:
                logger.info("  Headline enabled: Yes")
            logger.info(f"  Fullscreen: {template.layout.fullscreen_image}")
        except Exception as e:
            logger.warning(f"Failed to load template '{template_name}': {e}")
            logger.info("Continuing without template...")

    # Setup directories
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path("/tmp/bsforge_generate")
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Create sample scenes
    scenes, headline_keyword, headline_hook = create_sample_scenes()

    logger.info(f"\nScenes: {len(scenes)}")
    for i, scene in enumerate(scenes):
        marker = "← 의견" if scene.is_persona_scene else ""
        logger.info(f"  {i+1}. {scene.scene_type.value:12} {scene.text[:30]}... {marker}")

    # Persona style (colors for persona scenes)
    persona_style = PersonaStyleConfig(
        accent_color="#FF69B4",  # Hot pink
        secondary_color="#FFFF00",  # Yellow for emphasis
        use_persona_border=not template,
    )

    # Initialize components
    logger.info("\nInitializing components...")

    tts_factory = TTSEngineFactory()
    engine = tts_factory.get_engine("edge-tts")

    visual_config = VisualConfig()
    visual_manager = VisualSourcingManager(config=visual_config)

    subtitle_config = SubtitleConfig()
    subtitle_generator = SubtitleGenerator(config=subtitle_config)

    composition_config = CompositionConfig()
    compositor = FFmpegCompositor(config=composition_config, template=template)

    thumbnail_generator = ThumbnailGenerator()

    try:
        # Step 1: Generate TTS for each scene
        logger.info("\n[1/6] Generating TTS...")
        tts_config = TTSConfig(
            voice_id="ko-KR-InJoonNeural",
            speed=1.0,
            pitch=0,
            volume=0,
        )

        scene_tts_results = await engine.synthesize_scenes(
            scenes=scenes,
            config=tts_config,
            output_dir=temp_dir / "audio_scenes",
        )

        total_duration = sum(r.duration_seconds for r in scene_tts_results)
        logger.info(f"  {len(scene_tts_results)} scenes, {total_duration:.1f}s total")

        # Step 2: Concatenate audio
        logger.info("\n[2/6] Concatenating audio...")
        combined_tts = await concatenate_scene_audio(
            scene_results=scene_tts_results,
            output_path=output_dir / "audio",
        )
        logger.info(f"  Combined: {combined_tts.duration_seconds:.1f}s")

        # Step 3: Generate subtitles
        logger.info("\n[3/6] Generating subtitles...")
        subtitle_file = subtitle_generator.generate_from_scene_results(
            scene_results=scene_tts_results,
            scenes=scenes,
            persona_style=persona_style,
            template=template,
        )

        subtitle_path = subtitle_generator.to_ass_with_scene_styles(
            subtitle=subtitle_file,
            output_path=output_dir / "subtitle",
            scenes=scenes,
            scene_results=scene_tts_results,
            persona_style=persona_style,
            template=template,
        )
        logger.info(f"  {len(subtitle_file.segments)} segments")

        # Step 4: Source visuals
        logger.info("\n[4/6] Sourcing visuals...")
        scene_visuals = await visual_manager.source_visuals_for_scenes(
            scenes=scenes,
            scene_results=scene_tts_results,
            output_dir=temp_dir / "visuals",
        )

        sources = list({v.asset.source or "fallback" for v in scene_visuals})
        logger.info(f"  {len(scene_visuals)} visuals from: {sources}")

        # Step 5: Compose video
        logger.info("\n[5/6] Composing video...")
        if template and template.layout.headline:
            logger.info(f"  Headline: '{headline_keyword}' / '{headline_hook}'")

        composition_result = await compositor.compose_scenes(
            scenes=scenes,
            scene_tts_results=scene_tts_results,
            scene_visuals=scene_visuals,
            combined_audio_path=combined_tts.audio_path,
            subtitle_file=subtitle_path,
            output_path=output_dir / "video",
            persona_style=persona_style,
            headline_keyword=headline_keyword if template else None,
            headline_hook=headline_hook if template else None,
        )

        logger.info(f"  Duration: {composition_result.duration_seconds:.1f}s")
        logger.info(f"  Size: {composition_result.file_size_bytes / 1024 / 1024:.1f}MB")

        # Step 6: Generate thumbnail
        logger.info("\n[6/6] Generating thumbnail...")
        thumbnail_path = await thumbnail_generator.generate(
            title=f"{headline_keyword}\n{headline_hook}",
            output_path=output_dir / "thumbnail",
            background=scene_visuals[0].asset if scene_visuals else None,
        )

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("VIDEO GENERATION COMPLETE!")
        logger.info("=" * 60)
        logger.info(f"Video:     {composition_result.video_path}")
        logger.info(f"Audio:     {combined_tts.audio_path}")
        logger.info(f"Subtitle:  {subtitle_path}")
        logger.info(f"Thumbnail: {thumbnail_path}")
        logger.info("-" * 60)
        logger.info(f"Duration:   {composition_result.duration_seconds:.1f}s")
        logger.info(f"Resolution: {composition_result.resolution}")
        logger.info(f"FPS:        {composition_result.fps}")
        logger.info("=" * 60)

    finally:
        await visual_manager.close()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a YouTube Shorts video using BSForge scene pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic generation
  uv run python scripts/generate_video.py

  # With Korean Shorts template (headline + fullscreen)
  uv run python scripts/generate_video.py --template korean_shorts_standard

  # Custom output
  uv run python scripts/generate_video.py --output ./my_video
        """,
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("/workspace/outputs/generated_video"),
        help="Output directory (default: /workspace/outputs/generated_video)",
    )

    parser.add_argument(
        "--template",
        "-t",
        type=str,
        default=None,
        help="Video template name (e.g., korean_shorts_standard)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            generate_video(
                output_dir=args.output,
                template_name=args.template,
            )
        )
    except KeyboardInterrupt:
        logger.info("\nGeneration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
