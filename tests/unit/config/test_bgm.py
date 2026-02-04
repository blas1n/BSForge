"""Unit tests for BGM configuration models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.bgm import BGMConfig, BGMTrack


class TestBGMTrack:
    """Tests for BGMTrack model."""

    def test_valid_track(self):
        """Test creating a valid BGM track."""
        track = BGMTrack(
            name="Test Track",
            youtube_url="https://www.youtube.com/watch?v=abc123",
            tags=["chill", "ambient"],
        )
        assert track.name == "Test Track"
        assert str(track.youtube_url) == "https://www.youtube.com/watch?v=abc123"
        assert track.tags == ["chill", "ambient"]

    def test_minimal_track(self):
        """Test track with only required fields."""
        track = BGMTrack(
            name="Minimal",
            youtube_url="https://youtube.com/watch?v=test",
        )
        assert track.name == "Minimal"
        assert track.tags == []

    def test_empty_name_fails(self):
        """Test that empty name fails validation."""
        with pytest.raises(ValidationError):
            BGMTrack(name="", youtube_url="https://youtube.com/watch?v=test")

    def test_name_too_long_fails(self):
        """Test that name over 200 chars fails."""
        with pytest.raises(ValidationError):
            BGMTrack(name="x" * 201, youtube_url="https://youtube.com/watch?v=test")

    def test_invalid_url_fails(self):
        """Test that invalid URL fails validation."""
        with pytest.raises(ValidationError):
            BGMTrack(name="Test", youtube_url="not-a-url")


class TestBGMConfig:
    """Tests for BGMConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BGMConfig()
        assert config.enabled is False
        assert config.tracks == []
        assert config.volume == 0.1
        assert config.cache_dir == "data/bgm"
        assert config.selection_mode == "random"
        assert config.download_timeout == 300

    def test_enabled_with_tracks(self):
        """Test config with tracks enabled."""
        track = BGMTrack(
            name="Test Track",
            youtube_url="https://youtube.com/watch?v=abc",
        )
        config = BGMConfig(enabled=True, tracks=[track])
        assert config.enabled is True
        assert len(config.tracks) == 1

    def test_volume_range_valid(self):
        """Test valid volume values."""
        config = BGMConfig(volume=0.0)
        assert config.volume == 0.0

        config = BGMConfig(volume=1.0)
        assert config.volume == 1.0

        config = BGMConfig(volume=0.5)
        assert config.volume == 0.5

    def test_volume_range_invalid(self):
        """Test invalid volume values."""
        with pytest.raises(ValidationError):
            BGMConfig(volume=-0.1)

        with pytest.raises(ValidationError):
            BGMConfig(volume=1.1)

    def test_selection_mode_valid(self):
        """Test valid selection modes."""
        config = BGMConfig(selection_mode="random")
        assert config.selection_mode == "random"

        config = BGMConfig(selection_mode="sequential")
        assert config.selection_mode == "sequential"

    def test_selection_mode_invalid(self):
        """Test invalid selection mode fails."""
        with pytest.raises(ValidationError):
            BGMConfig(selection_mode="invalid")

    def test_download_timeout_range(self):
        """Test download timeout validation."""
        config = BGMConfig(download_timeout=30)
        assert config.download_timeout == 30

        config = BGMConfig(download_timeout=600)
        assert config.download_timeout == 600

        with pytest.raises(ValidationError):
            BGMConfig(download_timeout=29)

        with pytest.raises(ValidationError):
            BGMConfig(download_timeout=601)

    def test_get_cache_path(self):
        """Test cache path generation."""
        track = BGMTrack(
            name="My Test Track",
            youtube_url="https://youtube.com/watch?v=abc",
        )
        config = BGMConfig(cache_dir="custom/path")

        path = config.get_cache_path(track)
        assert path == Path("custom/path/My_Test_Track.mp3")

    def test_get_cache_path_sanitizes_name(self):
        """Test that special characters are sanitized in cache path."""
        track = BGMTrack(
            name="Track @#$% Name!",
            youtube_url="https://youtube.com/watch?v=abc",
        )
        config = BGMConfig()

        path = config.get_cache_path(track)
        # Special chars should be replaced with underscores
        assert "@" not in path.name
        assert "$" not in path.name
        assert "!" not in path.name
        assert path.suffix == ".mp3"
