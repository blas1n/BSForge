"""Tests for VideoGenerationPipeline."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.video import VideoGenerationConfig
from app.services.generator.compositor import CompositionResult
from app.services.generator.pipeline import VideoGenerationPipeline, VideoGenerationResult
from app.services.generator.subtitle import SubtitleFile
from app.services.generator.tts.base import TTSResult, WordTimestamp
from app.services.generator.visual.base import VisualAsset, VisualSourceType


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
    def configured_mocks(
        self,
        mock_tts_factory: MagicMock,
        mock_visual_manager: AsyncMock,
        mock_subtitle_generator: MagicMock,
        mock_compositor: AsyncMock,
        mock_ffmpeg_wrapper: AsyncMock,
        tmp_path: Path,
    ) -> dict:
        """Configure mocks with return values."""
        # TTS result
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake audio")
        tts_result = TTSResult(
            audio_path=audio_path,
            duration_seconds=10.0,
            word_timestamps=[
                WordTimestamp(word="Test", start=0.0, end=0.5),
            ],
        )
        mock_tts_factory.get_engine.return_value.synthesize = AsyncMock(return_value=tts_result)

        # Visual assets
        image_path = tmp_path / "visual.jpg"
        image_path.write_bytes(b"fake image")
        visual_asset = VisualAsset(
            type=VisualSourceType.STOCK_IMAGE,
            path=image_path,
            source="test",
            source_id="123",
        )
        mock_visual_manager.source_visuals = AsyncMock(return_value=[visual_asset])

        # Subtitle
        subtitle_file = SubtitleFile(segments=[])
        mock_subtitle_generator.generate_from_timestamps.return_value = subtitle_file
        subtitle_path = tmp_path / "subtitle.ass"
        subtitle_path.write_text("fake subtitle")
        mock_subtitle_generator.to_ass.return_value = subtitle_path

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
        mock_compositor.compose = AsyncMock(return_value=composition_result)

        # Thumbnail (extracted via ffmpeg)
        thumbnail_path = tmp_path / "thumbnail.jpg"
        thumbnail_path.write_bytes(b"fake thumbnail")
        mock_ffmpeg_wrapper.extract_frame.return_value = MagicMock()
        mock_ffmpeg_wrapper.run = AsyncMock()

        return {
            "tts_result": tts_result,
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
        mock_tts_factory: MagicMock,
        mock_visual_manager: AsyncMock,
        mock_compositor: AsyncMock,
        mock_ffmpeg_wrapper: AsyncMock,
    ) -> None:
        """Test that generate calls all required services."""
        result = await pipeline.generate(script=mock_script)

        assert isinstance(result, VideoGenerationResult)
        mock_tts_factory.get_engine.assert_called()
        mock_visual_manager.source_visuals.assert_called()
        mock_compositor.compose.assert_called()
        mock_ffmpeg_wrapper.extract_frame.assert_called()
        mock_ffmpeg_wrapper.run.assert_called()

    @pytest.mark.asyncio
    async def test_generate_returns_result(
        self,
        pipeline: VideoGenerationPipeline,
        configured_mocks: dict,
        mock_script: MagicMock,
    ) -> None:
        """Test that generate returns a VideoGenerationResult."""
        result = await pipeline.generate(script=mock_script)

        assert isinstance(result, VideoGenerationResult)
        assert result.video_path is not None
        assert result.thumbnail_path is not None
        assert result.audio_path is not None
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_generate_with_empty_script_raises(
        self,
        pipeline: VideoGenerationPipeline,
        mock_script: MagicMock,
    ) -> None:
        """Test that generating with empty script raises ValueError."""
        mock_script.script_text = ""

        with pytest.raises(ValueError, match="no text content"):
            await pipeline.generate(script=mock_script)


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

    def test_extract_keywords(
        self, pipeline: VideoGenerationPipeline, mock_script: MagicMock
    ) -> None:
        """Test keyword extraction from script."""
        mock_script.script_text = "Technology innovation blockchain cryptocurrency"
        mock_script.topic = None

        keywords = pipeline._extract_keywords(mock_script)

        assert len(keywords) > 0
        assert all(len(k) > 3 for k in keywords)
