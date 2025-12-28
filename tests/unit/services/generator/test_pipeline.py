"""Tests for VideoGenerationPipeline."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.video import VideoGenerationConfig
from app.models.scene import Scene, SceneScript, SceneType
from app.services.generator.compositor import CompositionResult
from app.services.generator.pipeline import VideoGenerationPipeline, VideoGenerationResult
from app.services.generator.subtitle import SubtitleFile
from app.services.generator.tts.base import TTSResult, WordTimestamp
from app.services.generator.visual.base import VisualAsset, VisualSourceType
from app.services.generator.visual.manager import SceneVisualResult


class TestVideoGenerationPipeline:
    """Test suite for VideoGenerationPipeline."""

    @pytest.fixture
    def pipeline(
        self,
        mock_tts_factory: MagicMock,
        mock_visual_manager: AsyncMock,
        mock_subtitle_generator: MagicMock,
        mock_compositor: AsyncMock,
        mock_ffmpeg_wrapper: AsyncMock,
        mock_db_session_factory: MagicMock,
        mock_template_loader: MagicMock,
        mock_bgm_manager: MagicMock,
        video_generation_config: VideoGenerationConfig,
        tmp_path: Path,
    ) -> VideoGenerationPipeline:
        """Create a VideoGenerationPipeline with mocked dependencies."""
        # Configure the config to use tmp_path
        video_generation_config.output_dir = str(tmp_path / "output")
        video_generation_config.temp_dir = str(tmp_path / "temp")

        return VideoGenerationPipeline(
            tts_factory=mock_tts_factory,
            visual_manager=mock_visual_manager,
            subtitle_generator=mock_subtitle_generator,
            compositor=mock_compositor,
            ffmpeg_wrapper=mock_ffmpeg_wrapper,
            db_session_factory=mock_db_session_factory,
            config=video_generation_config,
            template_loader=mock_template_loader,
            bgm_manager=mock_bgm_manager,
        )

    @pytest.fixture
    def mock_scene_script(self) -> SceneScript:
        """Create a mock scene script."""
        return SceneScript(
            scenes=[
                Scene(
                    scene_type=SceneType.HOOK,
                    text="테스트 시작합니다",
                    visual_keyword="test start",
                ),
                Scene(
                    scene_type=SceneType.CONTENT,
                    text="이것은 내용입니다",
                    visual_keyword="content info",
                ),
            ],
            headline="테스트, 시작",
        )

    @pytest.fixture
    def configured_mocks(
        self,
        mock_tts_factory: MagicMock,
        mock_visual_manager: AsyncMock,
        mock_subtitle_generator: MagicMock,
        mock_compositor: AsyncMock,
        mock_ffmpeg_wrapper: AsyncMock,
        tmp_path: Path,
    ) -> dict:
        """Configure mocks with return values for scene-based generation."""
        # Scene TTS results
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")
        tts_result = TTSResult(
            audio_path=audio_path,
            duration_seconds=5.0,
            word_timestamps=[
                WordTimestamp(word="Test", start=0.0, end=0.5),
            ],
        )
        # Return list of TTS results for scenes
        mock_tts_factory.get_engine.return_value.synthesize_scenes = AsyncMock(
            return_value=[tts_result, tts_result]
        )

        # Visual assets for scenes
        image_path = tmp_path / "visual.jpg"
        image_path.write_bytes(b"fake image")
        visual_asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            path=image_path,
            source="test",
            source_id="123",
        )
        scene_visual = SceneVisualResult(
            scene_index=0,
            scene_type="hook",
            asset=visual_asset,
            duration=5.0,
            start_offset=0.0,
        )
        mock_visual_manager.source_visuals_for_scenes = AsyncMock(
            return_value=[scene_visual, scene_visual]
        )

        # Subtitle
        subtitle_file = SubtitleFile(segments=[])
        mock_subtitle_generator.generate_from_scene_results.return_value = subtitle_file
        subtitle_path = tmp_path / "subtitle.ass"
        subtitle_path.write_text("fake subtitle")
        mock_subtitle_generator.to_ass_with_scene_styles.return_value = subtitle_path

        # Combined audio
        combined_audio_path = tmp_path / "combined_audio.mp3"
        combined_audio_path.write_bytes(b"fake combined audio")
        combined_tts_result = TTSResult(
            audio_path=combined_audio_path,
            duration_seconds=10.0,
            word_timestamps=[],
        )

        # Composition result
        video_path = tmp_path / "video.mp4"
        video_path.write_bytes(b"fake video")
        composition_result = CompositionResult(
            video_path=video_path,
            duration_seconds=10.0,
            file_size_bytes=1024,
            resolution="1080x1920",
            fps=30,
        )
        mock_compositor.compose_scenes = AsyncMock(return_value=composition_result)

        # Thumbnail (extracted via ffmpeg)
        thumbnail_path = tmp_path / "thumbnail.jpg"
        thumbnail_path.write_bytes(b"fake thumbnail")
        mock_ffmpeg_wrapper.extract_frame.return_value = MagicMock()
        mock_ffmpeg_wrapper.run = AsyncMock()
        # Mock concatenate_audio
        mock_ffmpeg_wrapper.concatenate_audio = AsyncMock()

        return {
            "tts_result": tts_result,
            "combined_tts_result": combined_tts_result,
            "visual_asset": visual_asset,
            "composition_result": composition_result,
            "thumbnail_path": thumbnail_path,
        }

    @pytest.mark.asyncio
    async def test_generate_calls_all_services(
        self,
        pipeline: VideoGenerationPipeline,
        configured_mocks: dict,
        mock_script: MagicMock,
        mock_scene_script: SceneScript,
        mock_tts_factory: MagicMock,
        mock_visual_manager: AsyncMock,
        mock_compositor: AsyncMock,
        mock_ffmpeg_wrapper: AsyncMock,
    ) -> None:
        """Test that generate calls all required services."""
        result = await pipeline.generate(
            script=mock_script,
            scene_script=mock_scene_script,
        )

        assert isinstance(result, VideoGenerationResult)
        mock_tts_factory.get_engine.assert_called()
        mock_visual_manager.source_visuals_for_scenes.assert_called()
        mock_compositor.compose_scenes.assert_called()
        mock_ffmpeg_wrapper.extract_frame.assert_called()
        mock_ffmpeg_wrapper.run.assert_called()

    @pytest.mark.asyncio
    async def test_generate_returns_result(
        self,
        pipeline: VideoGenerationPipeline,
        configured_mocks: dict,
        mock_script: MagicMock,
        mock_scene_script: SceneScript,
    ) -> None:
        """Test that generate returns a VideoGenerationResult."""
        result = await pipeline.generate(
            script=mock_script,
            scene_script=mock_scene_script,
        )

        assert isinstance(result, VideoGenerationResult)
        assert result.video_path is not None
        assert result.thumbnail_path is not None
        assert result.audio_path is not None
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_generate_with_empty_scenes_raises(
        self,
        pipeline: VideoGenerationPipeline,
        mock_script: MagicMock,
    ) -> None:
        """Test that generating with empty scenes raises ValueError."""
        # Create scene script with empty scenes - should fail validation
        with pytest.raises(ValueError, match="at least 1"):
            SceneScript(scenes=[], headline="테스트")


class TestVideoGenerationResult:
    """Test VideoGenerationResult dataclass."""

    def test_result_attributes(self, tmp_path: Path) -> None:
        """Test result has all required attributes."""
        video_path = tmp_path / "video.mp4"
        thumbnail_path = tmp_path / "thumbnail.jpg"
        audio_path = tmp_path / "audio.mp3"

        result = VideoGenerationResult(
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            audio_path=audio_path,
            subtitle_path=None,
            duration_seconds=60.0,
            file_size_bytes=10_000_000,
            tts_service="edge-tts",
            tts_voice_id="test-voice",
            visual_sources=["pexels"],
            generation_time_seconds=120,
        )

        assert result.video_path == video_path
        assert result.thumbnail_path == thumbnail_path
        assert result.duration_seconds == 60.0
        assert result.tts_service == "edge-tts"
        assert "pexels" in result.visual_sources


class TestPipelineHelpers:
    """Test pipeline helper methods."""

    @pytest.fixture
    def pipeline(
        self,
        mock_tts_factory: MagicMock,
        mock_visual_manager: AsyncMock,
        mock_subtitle_generator: MagicMock,
        mock_compositor: AsyncMock,
        mock_ffmpeg_wrapper: AsyncMock,
        mock_db_session_factory: MagicMock,
        mock_template_loader: MagicMock,
        mock_bgm_manager: MagicMock,
        video_generation_config: VideoGenerationConfig,
    ) -> VideoGenerationPipeline:
        """Create a pipeline for testing helper methods."""
        return VideoGenerationPipeline(
            tts_factory=mock_tts_factory,
            visual_manager=mock_visual_manager,
            subtitle_generator=mock_subtitle_generator,
            compositor=mock_compositor,
            ffmpeg_wrapper=mock_ffmpeg_wrapper,
            db_session_factory=mock_db_session_factory,
            config=video_generation_config,
            template_loader=mock_template_loader,
            bgm_manager=mock_bgm_manager,
        )

    def test_get_voice_for_script_korean(
        self, pipeline: VideoGenerationPipeline, mock_script: MagicMock
    ) -> None:
        """Test voice selection for Korean script."""
        mock_script.script_text = "안녕하세요. 이것은 테스트입니다."
        # Ensure no persona is set so fallback logic kicks in
        mock_script.channel = None

        voice_id = pipeline._get_voice_for_script(mock_script)

        assert voice_id is not None
        # Should select Korean voice (contains Korean character range detection)
        assert isinstance(voice_id, str)

    def test_get_voice_for_script_english(
        self, pipeline: VideoGenerationPipeline, mock_script: MagicMock
    ) -> None:
        """Test voice selection for English script."""
        mock_script.script_text = "Hello. This is a test."

        voice_id = pipeline._get_voice_for_script(mock_script)

        assert voice_id is not None
