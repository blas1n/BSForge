"""E2E tests for video generation pipeline.

These tests verify the complete video generation workflow:
1. TTS audio generation
2. Subtitle creation
3. Visual sourcing
4. FFmpeg composition
5. Thumbnail generation
"""

from pathlib import Path

import pytest

from app.config.video import CompositionConfig
from app.services.generator.compositor import FFmpegCompositor
from app.services.generator.subtitle import SubtitleGenerator
from app.services.generator.thumbnail import ThumbnailGenerator
from app.services.generator.tts.base import TTSConfig as TTSConfigDataclass
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.visual.fallback import FallbackGenerator


class TestTTSGeneration:
    """E2E tests for TTS generation."""

    @pytest.mark.asyncio
    async def test_edge_tts_korean(self, temp_output_dir: Path) -> None:
        """Test Edge TTS generates Korean audio."""
        engine = EdgeTTSEngine()
        config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        result = await engine.synthesize(
            text="안녕하세요. 테스트 음성입니다.",
            config=config,
            output_path=temp_output_dir / "test_audio",
        )

        assert result.audio_path.exists()
        assert result.duration_seconds > 0
        assert result.audio_path.suffix == ".mp3"

    @pytest.mark.asyncio
    async def test_edge_tts_english(self, temp_output_dir: Path) -> None:
        """Test Edge TTS generates English audio."""
        engine = EdgeTTSEngine()
        config = TTSConfigDataclass(voice_id="en-US-JennyNeural")

        result = await engine.synthesize(
            text="Hello, this is a test audio.",
            config=config,
            output_path=temp_output_dir / "test_audio_en",
        )

        assert result.audio_path.exists()
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_edge_tts_word_timestamps(self, temp_output_dir: Path) -> None:
        """Test Edge TTS can provide word-level timestamps.

        Note: Word timestamps availability depends on the Edge TTS service
        and the text content. We test with a longer sentence to increase
        the likelihood of getting timestamps.
        """
        engine = EdgeTTSEngine()
        config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        # Use a longer sentence for better timestamp extraction
        result = await engine.synthesize(
            text="안녕하세요. 오늘 날씨가 정말 좋습니다. 모두 좋은 하루 되세요.",
            config=config,
            output_path=temp_output_dir / "test_timestamps",
        )

        # Audio should always be generated
        assert result.audio_path.exists()
        assert result.duration_seconds > 0

        # Word timestamps may or may not be available depending on Edge TTS service
        # If they are available, verify they are properly ordered
        if result.word_timestamps:
            assert len(result.word_timestamps) > 0
            # Verify timestamps are ordered
            for i in range(1, len(result.word_timestamps)):
                assert result.word_timestamps[i].start >= result.word_timestamps[i - 1].start


class TestSubtitleGeneration:
    """E2E tests for subtitle generation."""

    def test_generate_from_script(self, temp_output_dir: Path) -> None:
        """Test subtitle generation from script text."""
        generator = SubtitleGenerator()

        subtitle_file = generator.generate_from_script(
            script="첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다.",
            audio_duration=10.0,
        )

        assert len(subtitle_file.segments) > 0

        # Export to SRT
        srt_path = generator.to_srt(subtitle_file, temp_output_dir / "test.srt")
        assert srt_path.exists()

        # Export to ASS
        ass_path = generator.to_ass(subtitle_file, temp_output_dir / "test.ass")
        assert ass_path.exists()

    @pytest.mark.asyncio
    async def test_subtitle_from_tts_timestamps(self, temp_output_dir: Path) -> None:
        """Test subtitle generation from TTS word timestamps."""
        # Generate TTS first
        engine = EdgeTTSEngine()
        config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        tts_result = await engine.synthesize(
            text="안녕하세요. 반갑습니다.",
            config=config,
            output_path=temp_output_dir / "tts_for_subs",
        )

        # Generate subtitles from timestamps
        generator = SubtitleGenerator()

        if tts_result.word_timestamps:
            subtitle_file = generator.generate_from_timestamps(tts_result.word_timestamps)
            assert len(subtitle_file.segments) > 0


class TestVisualSourcing:
    """E2E tests for visual sourcing."""

    @pytest.mark.asyncio
    async def test_fallback_generator(self, temp_output_dir: Path) -> None:
        """Test fallback visual generator creates images."""
        generator = FallbackGenerator()

        # Search for assets
        assets = await generator.search("test", max_results=2)
        assert len(assets) == 2

        # Download first asset
        downloaded = await generator.download(assets[0], temp_output_dir)
        assert downloaded.path is not None
        assert downloaded.path.exists()
        assert downloaded.width == 1080
        assert downloaded.height == 1920


class TestThumbnailGeneration:
    """E2E tests for thumbnail generation."""

    @pytest.mark.asyncio
    async def test_generate_thumbnail(self, temp_output_dir: Path) -> None:
        """Test thumbnail generation."""
        generator = ThumbnailGenerator()

        result = await generator.generate(
            title="테스트 썸네일 제목",
            output_path=temp_output_dir / "thumbnail.jpg",
        )

        assert result.exists()
        # Verify dimensions (default is 1080x1920 for YouTube Shorts portrait)
        from PIL import Image

        img = Image.open(result)
        assert img.size == (1080, 1920)


class TestFullVideoPipeline:
    """E2E tests for complete video generation pipeline."""

    @pytest.mark.asyncio
    async def test_complete_video_generation(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test complete video generation from script to final video."""
        script_text = "안녕하세요. 이것은 E2E 테스트입니다."

        # Step 1: Generate TTS
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        tts_result = await tts_engine.synthesize(
            text=script_text,
            config=tts_config,
            output_path=temp_output_dir / "audio",
        )

        assert tts_result.audio_path.exists()

        # Step 2: Generate subtitles
        subtitle_gen = SubtitleGenerator()

        if tts_result.word_timestamps:
            subtitle_file = subtitle_gen.generate_from_timestamps(tts_result.word_timestamps)
        else:
            subtitle_file = subtitle_gen.generate_from_script(
                script_text, tts_result.duration_seconds
            )

        subtitle_path = temp_output_dir / "subtitles.ass"
        subtitle_gen.to_ass(subtitle_file, subtitle_path)

        assert subtitle_path.exists()

        # Step 3: Generate background visual
        fallback_gen = FallbackGenerator()
        visuals = await fallback_gen.search("test", max_results=1)
        downloaded_visual = await fallback_gen.download(visuals[0], temp_output_dir)

        assert downloaded_visual.path is not None

        # Step 4: Compose video
        compositor = FFmpegCompositor(CompositionConfig())
        final_path = temp_output_dir / "final_video.mp4"

        result = await compositor.compose(
            audio=tts_result,
            visuals=[downloaded_visual],
            subtitle_file=subtitle_path,
            output_path=final_path,
        )

        assert final_path.exists()
        assert result.duration_seconds > 0
        assert result.file_size_bytes > 0

        # Step 5: Generate thumbnail
        thumb_gen = ThumbnailGenerator()
        thumb_path = await thumb_gen.generate(
            title="E2E 테스트 영상",
            output_path=temp_output_dir / "thumbnail.jpg",
        )

        assert thumb_path.exists()

    @pytest.mark.asyncio
    async def test_video_with_different_voices(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test video generation with different TTS voices."""
        tts_engine = EdgeTTSEngine()

        # Test male voice
        male_config = TTSConfigDataclass(voice_id="ko-KR-InJoonNeural")
        male_result = await tts_engine.synthesize(
            text="남성 음성 테스트입니다.",
            config=male_config,
            output_path=temp_output_dir / "male_audio",
        )

        assert male_result.audio_path.exists()

        # Test female voice
        female_config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")
        female_result = await tts_engine.synthesize(
            text="여성 음성 테스트입니다.",
            config=female_config,
            output_path=temp_output_dir / "female_audio",
        )

        assert female_result.audio_path.exists()


class TestVideoQuality:
    """Tests for video output quality."""

    @pytest.mark.asyncio
    async def test_video_specs(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test video meets YouTube Shorts specifications."""
        import subprocess

        # Generate a simple video
        tts_engine = EdgeTTSEngine()
        config = TTSConfigDataclass(voice_id="ko-KR-SunHiNeural")

        tts_result = await tts_engine.synthesize(
            text="품질 테스트",
            config=config,
            output_path=temp_output_dir / "quality_audio",
        )

        fallback_gen = FallbackGenerator()
        visuals = await fallback_gen.search("test", max_results=1)
        visual = await fallback_gen.download(visuals[0], temp_output_dir)

        compositor = FFmpegCompositor(CompositionConfig())
        final_path = temp_output_dir / "quality_test.mp4"

        await compositor.compose(
            audio=tts_result,
            visuals=[visual],
            subtitle_file=None,
            output_path=final_path,
        )

        # Check video specs with ffprobe
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,codec_name",
                "-of",
                "csv=p=0",
                str(final_path),
            ],
            capture_output=True,
            text=True,
        )

        parts = result.stdout.strip().split(",")
        codec = parts[0]
        width = int(parts[1])
        height = int(parts[2])

        # Verify YouTube Shorts specs
        assert codec == "h264", "Should use H.264 codec"
        assert width == 1080, "Should be 1080 pixels wide"
        assert height == 1920, "Should be 1920 pixels tall (9:16 aspect ratio)"


class TestSceneBasedPipeline:
    """E2E tests for scene-based video generation pipeline."""

    @pytest.mark.asyncio
    async def test_scene_based_video_generation(
        self,
        temp_output_dir: Path,
        skip_without_ffmpeg: None,
    ) -> None:
        """Test complete scene-based video generation."""
        from app.models.scene import Scene, SceneScript, SceneType, VisualHintType
        from app.services.generator.tts.utils import concatenate_scene_audio

        # Create sample scenes
        scenes = [
            Scene(
                scene_type=SceneType.HOOK,
                text="테스트 시작합니다",
                keyword="test start",
                visual_hint=VisualHintType.STOCK_IMAGE,
            ),
            Scene(
                scene_type=SceneType.CONTENT,
                text="이것은 내용입니다",
                keyword="content",
                visual_hint=VisualHintType.STOCK_IMAGE,
            ),
            Scene(
                scene_type=SceneType.CONCLUSION,
                text="마무리합니다",
                keyword="end",
                visual_hint=VisualHintType.STOCK_IMAGE,
            ),
        ]

        scene_script = SceneScript(
            scenes=scenes,
            headline_keyword="테스트",
            headline_hook="E2E 검증",
        )

        # Step 1: Generate TTS for each scene
        tts_engine = EdgeTTSEngine()
        tts_config = TTSConfigDataclass(voice_id="ko-KR-InJoonNeural", speed=1.1)

        scene_tts_results = await tts_engine.synthesize_scenes(
            scenes=scenes,
            config=tts_config,
            output_dir=temp_output_dir / "audio_scenes",
        )

        assert len(scene_tts_results) == len(scenes)
        for result in scene_tts_results:
            assert result.audio_path.exists()

        # Step 2: Concatenate audio
        combined_tts = await concatenate_scene_audio(
            scene_results=scene_tts_results,
            output_path=temp_output_dir / "combined_audio",
        )

        assert combined_tts.audio_path.exists()
        assert combined_tts.duration_seconds > 0

        # Step 3: Generate subtitles
        subtitle_gen = SubtitleGenerator()
        subtitle_file = subtitle_gen.generate_from_scene_results(
            scene_results=scene_tts_results,
            scenes=scenes,
        )

        subtitle_path = temp_output_dir / "subtitles.ass"
        subtitle_gen.to_ass(subtitle_file, subtitle_path)

        assert subtitle_path.exists()

        # Step 4: Generate visuals
        fallback_gen = FallbackGenerator()
        visuals = []
        for i, tts_result in enumerate(scene_tts_results):
            assets = await fallback_gen.search(f"scene_{i}", max_results=1)
            downloaded = await fallback_gen.download(assets[0], temp_output_dir / "visuals")
            downloaded.duration = tts_result.duration_seconds
            visuals.append(downloaded)

        assert len(visuals) == len(scenes)

        # Step 5: Compose video
        from app.services.generator.visual.manager import SceneVisualResult

        current_offset = 0.0
        scene_visuals = []
        for i, (scene, visual, tts_result) in enumerate(
            zip(scenes, visuals, scene_tts_results, strict=False)
        ):
            scene_visuals.append(
                SceneVisualResult(
                    scene_index=i,
                    scene_type=scene.scene_type.value,
                    asset=visual,
                    duration=tts_result.duration_seconds,
                    start_offset=current_offset,
                )
            )
            current_offset += tts_result.duration_seconds

        compositor = FFmpegCompositor(CompositionConfig())
        final_path = temp_output_dir / "scene_video.mp4"

        result = await compositor.compose_scenes(
            scenes=scenes,
            scene_tts_results=scene_tts_results,
            scene_visuals=scene_visuals,
            combined_audio_path=combined_tts.audio_path,
            subtitle_file=subtitle_path,
            output_path=final_path,
            headline_keyword=scene_script.headline_keyword,
            headline_hook=scene_script.headline_hook,
        )

        assert final_path.exists()
        assert result.duration_seconds > 0
