"""Pytest fixtures for generator service tests."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.video import (
    CompositionConfig,
    SubtitleConfig,
    ThumbnailConfig,
    TTSConfig,
    VideoGenerationConfig,
    VisualConfig,
)
from app.models.script import Script
from app.services.generator.tts.base import TTSResult, WordTimestamp
from app.services.generator.visual.base import VisualAsset, VisualSourceType


@pytest.fixture
def mock_script() -> MagicMock:
    """Create a mock Script for testing."""
    script = MagicMock(spec=Script)
    script.id = uuid.uuid4()
    script.channel_id = uuid.uuid4()
    script.script_text = "This is a test script for video generation."
    script.hook = "Hook section"
    script.body = "Body section"
    script.conclusion = "Conclusion section"
    script.topic = None  # Explicitly set to None for fallback behavior
    script.channel = None  # Explicitly set to None
    return script


@pytest.fixture
def mock_tts_result(tmp_path: Path) -> TTSResult:
    """Create a mock TTS result for testing."""
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio data")

    return TTSResult(
        audio_path=audio_path,
        duration_seconds=10.5,
        word_timestamps=[
            WordTimestamp(word="This", start=0.0, end=0.3),
            WordTimestamp(word="is", start=0.3, end=0.5),
            WordTimestamp(word="a", start=0.5, end=0.6),
            WordTimestamp(word="test", start=0.6, end=1.0),
        ],
    )


@pytest.fixture
def mock_visual_asset(tmp_path: Path) -> VisualAsset:
    """Create a mock visual asset for testing."""
    image_path = tmp_path / "visual.jpg"
    image_path.write_bytes(b"fake image data")

    return VisualAsset(
        type=VisualSourceType.STOCK_IMAGE,
        url="https://example.com/image.jpg",
        path=image_path,
        width=1080,
        height=1920,
        duration=5.0,
        source="pexels",
        source_id="12345",
    )


@pytest.fixture
def mock_video_asset(tmp_path: Path) -> VisualAsset:
    """Create a mock video asset for testing."""
    video_path = tmp_path / "visual.mp4"
    video_path.write_bytes(b"fake video data")

    return VisualAsset(
        type=VisualSourceType.STOCK_VIDEO,
        url="https://example.com/video.mp4",
        path=video_path,
        width=1080,
        height=1920,
        duration=8.0,
        source="pexels",
        source_id="67890",
    )


@pytest.fixture
def tts_config() -> TTSConfig:
    """Create a TTS config for testing."""
    return TTSConfig()


@pytest.fixture
def subtitle_config() -> SubtitleConfig:
    """Create a subtitle config for testing."""
    return SubtitleConfig()


@pytest.fixture
def visual_config() -> VisualConfig:
    """Create a visual config for testing."""
    return VisualConfig()


@pytest.fixture
def composition_config() -> CompositionConfig:
    """Create a composition config for testing."""
    return CompositionConfig()


@pytest.fixture
def thumbnail_config() -> ThumbnailConfig:
    """Create a thumbnail config for testing."""
    return ThumbnailConfig()


@pytest.fixture
def video_generation_config() -> VideoGenerationConfig:
    """Create a video generation config for testing."""
    return VideoGenerationConfig()


@pytest.fixture
def mock_tts_factory() -> MagicMock:
    """Create a mock TTS factory."""
    factory = MagicMock()
    engine = AsyncMock()
    engine.synthesize = AsyncMock()
    factory.get_engine.return_value = engine
    return factory


@pytest.fixture
def mock_visual_manager() -> AsyncMock:
    """Create a mock visual manager."""
    manager = AsyncMock()
    manager.source_visuals = AsyncMock(return_value=[])
    return manager


@pytest.fixture
def mock_subtitle_generator() -> MagicMock:
    """Create a mock subtitle generator."""
    generator = MagicMock()
    generator.generate_from_timestamps = MagicMock()
    generator.generate_from_script = MagicMock()
    generator.to_ass = MagicMock()
    generator.to_srt = MagicMock()
    return generator


@pytest.fixture
def mock_compositor() -> AsyncMock:
    """Create a mock compositor."""
    compositor = AsyncMock()
    compositor.compose = AsyncMock()
    return compositor


@pytest.fixture
def mock_thumbnail_generator() -> AsyncMock:
    """Create a mock thumbnail generator."""
    generator = AsyncMock()
    generator.generate = AsyncMock()
    return generator


@pytest.fixture
def mock_db_session_factory() -> MagicMock:
    """Create a mock database session factory."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory
