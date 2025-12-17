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

    # yt-dlp for BGM download
    deps["yt_dlp"] = shutil.which("yt-dlp") is not None

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


async def demo_bgm() -> Path | None:
    """Demo BGM download and selection."""
    print("\n" + "=" * 50)
    print("5. BGM (Background Music) Demo")
    print("=" * 50)

    try:
        from app.config.bgm import BGMConfig, BGMTrack
        from app.services.generator.bgm import BGMManager

        # Create BGM config with real YouTube Audio Library tracks
        bgm_config = BGMConfig(
            enabled=True,
            volume=0.08,
            cache_dir="/workspace/data/bgm",
            selection_mode="random",
            tracks=[
                BGMTrack(
                    name="upbeat_corporate",
                    youtube_url="https://www.youtube.com/watch?v=cxWhnfQtcug",
                ),
                BGMTrack(
                    name="modern_technology",
                    youtube_url="https://www.youtube.com/watch?v=Hiq53IyRnGI",
                ),
            ],
        )

        print("\nBGM Config:")
        print(f"  Enabled: {bgm_config.enabled}")
        print(f"  Volume: {bgm_config.volume}")
        print(f"  Cache dir: {bgm_config.cache_dir}")
        print(f"  Tracks: {len(bgm_config.tracks)}")

        # Initialize BGM manager (downloads tracks if not cached)
        print("\nInitializing BGM Manager (downloading if needed)...")
        bgm_manager = BGMManager(bgm_config)
        await bgm_manager.initialize()

        print(f"  Cached: {bgm_manager.cached_track_count}/{bgm_manager.track_count}")

        # Select a BGM track
        bgm_path = await bgm_manager.get_bgm_for_video()
        if bgm_path:
            print(f"\nSelected BGM: {bgm_path.name}")
            print(f"  Path: {bgm_path}")
            size_mb = bgm_path.stat().st_size / (1024 * 1024)
            print(f"  Size: {size_mb:.2f} MB")
            return bgm_path
        else:
            print("\nNo BGM available")
            return None

    except Exception as e:
        print(f"BGM Error: {e}")
        import traceback

        traceback.print_exc()
        return None


async def demo_full_video(with_bgm: bool = True) -> Path | None:
    """Demo full video generation pipeline with optional BGM."""
    print("\n" + "=" * 50)
    print("6. Full Video Generation Demo" + (" (with BGM)" if with_bgm else ""))
    print("=" * 50)

    try:
        from app.config.bgm import BGMConfig, BGMTrack
        from app.config.video import CompositionConfig
        from app.services.generator.bgm import BGMManager
        from app.services.generator.compositor import FFmpegCompositor
        from app.services.generator.subtitle import SubtitleGenerator
        from app.services.generator.tts.base import TTSConfig
        from app.services.generator.tts.edge import EdgeTTSEngine
        from app.services.generator.visual.fallback import FallbackGenerator

        output_dir = Path("/tmp/bsforge_demo")
        output_dir.mkdir(exist_ok=True)

        # Step 1: Initialize BGM if enabled
        bgm_path = None
        bgm_volume = 0.08
        if with_bgm:
            print("\nStep 1: Initializing BGM...")
            bgm_config = BGMConfig(
                enabled=True,
                volume=bgm_volume,
                cache_dir="/workspace/data/bgm",
                selection_mode="random",
                tracks=[
                    BGMTrack(
                        name="upbeat_corporate",
                        youtube_url="https://www.youtube.com/watch?v=cxWhnfQtcug",
                    ),
                ],
            )
            bgm_manager = BGMManager(bgm_config)
            await bgm_manager.initialize()
            bgm_path = await bgm_manager.get_bgm_for_video()
            if bgm_path:
                print(f"  BGM: {bgm_path.name}")
            else:
                print("  BGM: Not available (will generate without music)")

        # Step 2: Generate TTS
        print("\nStep 2: Generating TTS audio...")
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfig(voice_id="ko-KR-InJoonNeural", speed=1.1)

        script_text = """안녕하세요, AI테크브로입니다!
오늘은 최신 AI 트렌드에 대해 알아보겠습니다.
ChatGPT, Claude, Gemini까지,
AI가 우리 일상을 어떻게 바꾸고 있는지 살펴볼게요.
이 영상도 AI가 자동으로 만들어낸 거랍니다!"""

        tts_result = await tts_engine.synthesize(
            text=script_text,
            config=tts_config,
            output_path=output_dir / "video_audio",
        )
        print(f"  Audio: {tts_result.audio_path} ({tts_result.duration_seconds:.1f}s)")

        # Step 3: Generate subtitles from word timestamps
        print("\nStep 3: Generating subtitles...")
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

        # Step 4: Generate background visual
        print("\nStep 4: Generating background visual...")
        fallback_gen = FallbackGenerator()
        visual_assets = await fallback_gen.search("AI technology", max_results=1)

        if visual_assets:
            downloaded_asset = await fallback_gen.download(visual_assets[0], output_dir)
            print(f"  Background: {downloaded_asset.path}")
        else:
            print("  ERROR: No visual assets generated")
            return None

        # Step 5: Compose video with FFmpeg (with BGM if available)
        print("\nStep 5: Composing video with FFmpeg...")
        composition_config = CompositionConfig(background_music_volume=bgm_volume)
        compositor = FFmpegCompositor(composition_config)

        final_video_path = (
            output_dir / "final_video_with_bgm.mp4" if bgm_path else output_dir / "final_video.mp4"
        )

        result = await compositor.compose(
            audio=tts_result,
            visuals=[downloaded_asset],
            subtitle_file=subtitle_path,
            output_path=final_video_path,
            background_music_path=bgm_path,
        )

        if result.video_path.exists():
            size_mb = result.video_path.stat().st_size / (1024 * 1024)
            print("\n" + "=" * 50)
            print("  VIDEO GENERATED SUCCESSFULLY!")
            print("=" * 50)
            print(f"  Output: {result.video_path}")
            print(f"  Size: {size_mb:.2f} MB")
            print(f"  Duration: {result.duration_seconds:.1f} seconds")
            if bgm_path:
                print(f"  BGM: {bgm_path.name} (volume: {bgm_volume*100:.0f}%)")
            return result.video_path
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

    # BGM demo (only if yt-dlp available)
    if deps["yt_dlp"]:
        await demo_bgm()
    else:
        print("\n[Skip] BGM demo - yt-dlp not installed")

    # Full video generation (only if FFmpeg available)
    if deps["ffmpeg"]:
        # Generate with BGM if yt-dlp available
        await demo_full_video(with_bgm=deps["yt_dlp"])

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

    # BGM cache directory
    bgm_dir = Path("/workspace/data/bgm")
    if bgm_dir.exists():
        print("\nBGM cache directory: /workspace/data/bgm/")
        for f in sorted(bgm_dir.iterdir()):
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

    # yt-dlp status
    if not deps["yt_dlp"]:
        print("\n" + "-" * 50)
        print("NOTE: yt-dlp is not installed.")
        print("BGM download requires yt-dlp.")
        print("Install with: pip install yt-dlp")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())
