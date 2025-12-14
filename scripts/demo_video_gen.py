#!/usr/bin/env python
"""Demo script for video generation pipeline.

This script demonstrates the video generation capabilities.
Run with: uv run python scripts/demo_video_gen.py
"""

import asyncio
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def check_dependencies() -> dict[str, bool]:
    """Check which dependencies are available."""
    deps = {}

    # FFmpeg
    deps["ffmpeg"] = shutil.which("ffmpeg") is not None

    # Edge TTS (free, no API key)
    try:
        import importlib.util

        deps["edge_tts"] = importlib.util.find_spec("edge_tts") is not None
    except ImportError:
        deps["edge_tts"] = False

    # PIL for thumbnails
    try:
        import importlib.util

        deps["pillow"] = importlib.util.find_spec("PIL") is not None
    except ImportError:
        deps["pillow"] = False

    # API Keys
    import os

    deps["pexels_api"] = bool(os.getenv("PEXELS_API_KEY"))
    deps["openai_api"] = bool(os.getenv("OPENAI_API_KEY"))
    deps["elevenlabs_api"] = bool(os.getenv("ELEVENLABS_API_KEY"))

    return deps


async def demo_tts() -> Path | None:
    """Demo TTS generation."""
    print("\n" + "=" * 50)
    print("1. TTS (Text-to-Speech) Demo")
    print("=" * 50)

    try:
        from app.services.generator.tts.base import TTSConfig
        from app.services.generator.tts.edge import EdgeTTSEngine

        engine = EdgeTTSEngine()

        # Get available Korean voices
        voices = engine.get_available_voices("ko")
        print(f"Available Korean voices: {len(voices)}")
        for v in voices[:3]:
            print(f"  - {v.voice_id}: {v.name} ({v.gender})")

        # Generate speech
        output_dir = Path("/tmp/bsforge_demo")
        output_dir.mkdir(exist_ok=True)
        audio_path = output_dir / "demo_audio"

        text = "안녕하세요! BSForge 비디오 생성 데모입니다. AI가 자동으로 영상을 만들어드립니다."

        print(f"\nGenerating speech for: '{text[:50]}...'")

        config = TTSConfig(voice_id="ko-KR-SunHiNeural")
        result = await engine.synthesize(
            text=text,
            config=config,
            output_path=audio_path,
        )

        print(f"Audio saved to: {result.audio_path}")
        print(f"Duration: {result.duration_seconds:.2f} seconds")

        if result.word_timestamps:
            print(f"Word timestamps: {len(result.word_timestamps)} words")
            print("\nSample word timestamps:")
            for wt in result.word_timestamps[:5]:
                print(f"  [{wt.start:.2f}s - {wt.end:.2f}s] '{wt.word}'")

        return result.audio_path

    except Exception as e:
        print(f"TTS Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def demo_subtitle(audio_duration: float = 5.0) -> Path | None:
    """Demo subtitle generation."""
    print("\n" + "=" * 50)
    print("2. Subtitle Generation Demo")
    print("=" * 50)

    try:
        from app.services.generator.subtitle import SubtitleGenerator
        from app.services.generator.tts.base import WordTimestamp

        generator = SubtitleGenerator()

        # Create sample word timestamps (using correct field names: start, end)
        timestamps = [
            WordTimestamp(word="안녕하세요!", start=0.0, end=0.8),
            WordTimestamp(word="BSForge", start=0.9, end=1.4),
            WordTimestamp(word="비디오", start=1.5, end=1.9),
            WordTimestamp(word="생성", start=2.0, end=2.4),
            WordTimestamp(word="데모입니다.", start=2.5, end=3.2),
        ]

        subtitle_file = generator.generate_from_timestamps(timestamps)

        print(f"Generated {len(subtitle_file.segments)} subtitle segments")

        # Export to SRT
        output_dir = Path("/tmp/bsforge_demo")
        output_dir.mkdir(exist_ok=True)
        srt_path = output_dir / "demo_subtitles.srt"

        # to_srt now takes output_path and returns it
        result_path = generator.to_srt(subtitle_file, srt_path)
        print(f"\nSRT saved to: {result_path}")
        print("\nSRT Content:")
        print("-" * 30)
        print(srt_path.read_text(encoding="utf-8"))

        # Export to ASS (with styling)
        ass_path = output_dir / "demo_subtitles.ass"
        generator.to_ass(subtitle_file, ass_path)
        print(f"\nASS saved to: {ass_path}")

        return srt_path

    except Exception as e:
        print(f"Subtitle Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def demo_thumbnail() -> Path | None:
    """Demo thumbnail generation."""
    print("\n" + "=" * 50)
    print("3. Thumbnail Generation Demo")
    print("=" * 50)

    try:
        from app.services.generator.thumbnail import ThumbnailGenerator

        generator = ThumbnailGenerator()

        output_dir = Path("/tmp/bsforge_demo")
        output_dir.mkdir(exist_ok=True)
        thumb_path = output_dir / "demo_thumbnail.jpg"

        title = "AI가 만든 놀라운 영상!"

        print(f"Generating thumbnail for: '{title}'")

        result = await generator.generate(
            title=title,
            output_path=thumb_path,
            background_color="#1a1a2e",
        )

        print(f"Thumbnail saved to: {result}")
        print("Size: 1280x720 (YouTube recommended)")

        return result

    except Exception as e:
        print(f"Thumbnail Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def demo_fallback_visual() -> Path | None:
    """Demo fallback visual generation (no API needed)."""
    print("\n" + "=" * 50)
    print("4. Fallback Visual Generation Demo")
    print("=" * 50)

    try:
        from app.services.generator.visual.fallback import FallbackGenerator

        generator = FallbackGenerator()

        output_dir = Path("/tmp/bsforge_demo")
        output_dir.mkdir(exist_ok=True)

        # Search for visuals (query is str, not list)
        assets = await generator.search("technology AI", max_results=2)

        print(f"Generated {len(assets)} fallback assets")

        # Download one
        if assets:
            asset = assets[0]
            # download() takes output_dir (directory), returns asset with path set
            downloaded = await generator.download(asset, output_dir)

            print(f"Visual saved to: {downloaded.path}")
            print(f"Type: {downloaded.type}")
            print(f"Size: {downloaded.width}x{downloaded.height}")

            return downloaded.path

        return None

    except Exception as e:
        print(f"Visual Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def demo_full_video() -> Path | None:
    """Demo full video generation pipeline."""
    print("\n" + "=" * 50)
    print("5. Full Video Generation Demo")
    print("=" * 50)

    try:
        from app.config.video import CompositionConfig
        from app.services.generator.compositor import FFmpegCompositor
        from app.services.generator.subtitle import SubtitleGenerator
        from app.services.generator.tts.base import TTSConfig
        from app.services.generator.tts.edge import EdgeTTSEngine
        from app.services.generator.visual.fallback import FallbackGenerator

        output_dir = Path("/tmp/bsforge_demo")
        output_dir.mkdir(exist_ok=True)

        # Step 1: Generate TTS
        print("\nStep 1: Generating TTS audio...")
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfig(voice_id="ko-KR-SunHiNeural")

        script_text = "안녕하세요! 이것은 BSForge로 자동 생성된 YouTube Shorts 영상입니다. AI가 음성, 자막, 배경까지 모두 만들어냈습니다."

        tts_result = await tts_engine.synthesize(
            text=script_text,
            config=tts_config,
            output_path=output_dir / "video_audio",
        )
        print(f"  Audio: {tts_result.audio_path} ({tts_result.duration_seconds:.1f}s)")

        # Step 2: Generate subtitles from word timestamps
        print("\nStep 2: Generating subtitles...")
        subtitle_gen = SubtitleGenerator()

        if tts_result.word_timestamps:
            subtitle_file = subtitle_gen.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_gen.generate_from_script(
                script_text, tts_result.duration_seconds
            )

        subtitle_path = output_dir / "video_subtitles.ass"
        subtitle_gen.to_ass(subtitle_file, subtitle_path)
        print(f"  Subtitles: {subtitle_path} ({len(subtitle_file.segments)} segments)")

        # Step 3: Generate background visual
        print("\nStep 3: Generating background visual...")
        fallback_gen = FallbackGenerator()
        visual_assets = await fallback_gen.search("AI technology", max_results=1)

        if visual_assets:
            # download() takes output_dir (directory), not output_path (file)
            downloaded_asset = await fallback_gen.download(visual_assets[0], output_dir)
            print(f"  Background: {downloaded_asset.path}")
        else:
            print("  ERROR: No visual assets generated")
            return None

        # Step 4: Compose video with FFmpeg
        print("\nStep 4: Composing video with FFmpeg...")
        compositor = FFmpegCompositor(CompositionConfig())

        final_video_path = output_dir / "final_video.mp4"

        # Use compose() method with proper parameters
        await compositor.compose(
            audio=tts_result,
            visuals=[downloaded_asset],
            subtitle_file=subtitle_path,
            output_path=final_video_path,
        )

        if final_video_path.exists():
            size_mb = final_video_path.stat().st_size / (1024 * 1024)
            print("\n  VIDEO GENERATED SUCCESSFULLY!")
            print(f"  Output: {final_video_path}")
            print(f"  Size: {size_mb:.2f} MB")
            print(f"  Duration: {tts_result.duration_seconds:.1f} seconds")
            return final_video_path
        else:
            print("  Video generation failed!")
            return None

    except Exception as e:
        print(f"Full Video Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def main() -> None:
    """Run all demos."""
    print("=" * 50)
    print("BSForge Video Generation Demo")
    print("=" * 50)

    # Check dependencies
    deps = await check_dependencies()
    print("\nDependency Status:")
    for name, available in deps.items():
        status = "OK" if available else "MISSING"
        print(f"  {name}: {status}")

    # Run demos
    await demo_tts()
    await demo_subtitle()
    await demo_thumbnail()
    await demo_fallback_visual()

    # Full video generation (only if FFmpeg available)
    if deps["ffmpeg"]:
        await demo_full_video()

    # Summary
    print("\n" + "=" * 50)
    print("Demo Summary")
    print("=" * 50)
    print("Output directory: /tmp/bsforge_demo/")
    print("\nGenerated files:")

    output_dir = Path("/tmp/bsforge_demo")
    if output_dir.exists():
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                size = f.stat().st_size
                print(f"  - {f.name} ({size:,} bytes)")

    # FFmpeg status
    if not deps["ffmpeg"]:
        print("\n" + "-" * 50)
        print("NOTE: FFmpeg is not installed.")
        print("Full video composition requires FFmpeg.")
        print("In DevContainer, FFmpeg should be pre-installed.")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())
