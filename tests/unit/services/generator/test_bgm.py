"""Tests for BGM services."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.bgm import BGMConfig, BGMTrack
from app.core.exceptions import BGMDownloadError
from app.services.generator.bgm.downloader import BGMDownloader
from app.services.generator.bgm.manager import BGMManager
from app.services.generator.bgm.selector import BGMSelector


class TestBGMConfig:
    """Test BGM configuration models."""

    def test_default_config(self) -> None:
        """Test default BGM configuration."""
        config = BGMConfig()
        assert config.enabled is False
        assert config.volume == 0.1
        assert config.cache_dir == "data/bgm"
        assert config.selection_mode == "random"
        assert config.download_timeout == 300
        assert config.tracks == []

    def test_config_with_tracks(self) -> None:
        """Test BGMConfig with tracks."""
        config = BGMConfig(
            enabled=True,
            volume=0.15,
            cache_dir="/custom/path",
            tracks=[
                BGMTrack(
                    name="track1",
                    youtube_url="https://www.youtube.com/watch?v=test123",
                ),
            ],
        )
        assert config.enabled is True
        assert config.volume == 0.15
        assert len(config.tracks) == 1
        assert config.tracks[0].name == "track1"

    def test_track_config(self) -> None:
        """Test BGMTrack configuration."""
        track = BGMTrack(
            name="test_track",
            youtube_url="https://www.youtube.com/watch?v=test123",
            tags=["upbeat", "tech"],
        )
        assert track.name == "test_track"
        assert "youtube" in str(track.youtube_url)
        assert track.tags == ["upbeat", "tech"]

    def test_get_cache_path(self, tmp_path: Path) -> None:
        """Test get_cache_path method."""
        config = BGMConfig(cache_dir=str(tmp_path))
        track = BGMTrack(
            name="my-track",
            youtube_url="https://www.youtube.com/watch?v=test",
        )
        cache_path = config.get_cache_path(track)
        assert cache_path == tmp_path / "my-track.mp3"

    def test_get_cache_path_sanitizes_name(self, tmp_path: Path) -> None:
        """Test that get_cache_path sanitizes special characters."""
        config = BGMConfig(cache_dir=str(tmp_path))
        track = BGMTrack(
            name="my track/with:special*chars",
            youtube_url="https://www.youtube.com/watch?v=test",
        )
        cache_path = config.get_cache_path(track)
        # Should replace special chars with underscore
        assert ":" not in cache_path.name
        assert "/" not in cache_path.name
        assert "*" not in cache_path.name


class TestBGMDownloader:
    """Test BGM downloader."""

    @pytest.fixture
    def config(self, tmp_path: Path) -> BGMConfig:
        """Create test config."""
        return BGMConfig(
            enabled=True,
            cache_dir=str(tmp_path / "bgm"),
        )

    @pytest.fixture
    def track(self) -> BGMTrack:
        """Create test track."""
        return BGMTrack(
            name="test_track",
            youtube_url="https://www.youtube.com/watch?v=test123",
        )

    def test_init_creates_cache_dir(self, config: BGMConfig) -> None:
        """Test that __init__ creates cache directory."""
        _ = BGMDownloader(config)
        assert Path(config.cache_dir).exists()

    def test_is_cached_false(self, config: BGMConfig, track: BGMTrack) -> None:
        """Test is_cached returns False for uncached track."""
        downloader = BGMDownloader(config)
        assert downloader.is_cached(track) is False

    def test_is_cached_true(self, config: BGMConfig, track: BGMTrack, tmp_path: Path) -> None:
        """Test is_cached returns True for cached track."""
        # Create cache file
        cache_dir = tmp_path / "bgm"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "test_track.mp3"
        cache_file.write_bytes(b"fake audio")

        downloader = BGMDownloader(config)
        assert downloader.is_cached(track) is True

    @pytest.mark.asyncio
    async def test_download_skips_cached(
        self, config: BGMConfig, track: BGMTrack, tmp_path: Path
    ) -> None:
        """Test download skips already cached files."""
        # Create cache file
        cache_dir = tmp_path / "bgm"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "test_track.mp3"
        cache_file.write_bytes(b"fake audio")

        downloader = BGMDownloader(config)
        path = await downloader.download(track)

        assert path == cache_file

    @pytest.mark.asyncio
    async def test_download_raises_on_yt_dlp_error(
        self, config: BGMConfig, track: BGMTrack
    ) -> None:
        """Test download raises when yt-dlp fails."""
        downloader = BGMDownloader(config)

        with patch.object(
            downloader,
            "_download_sync",
            side_effect=BGMDownloadError("yt-dlp failed", track.name, str(track.youtube_url)),
        ):
            with pytest.raises(BGMDownloadError) as exc_info:
                await downloader.download(track)
            assert "yt-dlp failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ensure_all_downloaded_handles_errors(self, config: BGMConfig) -> None:
        """Test ensure_all_downloaded continues on errors."""
        tracks = [
            BGMTrack(name="track1", youtube_url="https://youtube.com/watch?v=1"),
            BGMTrack(name="track2", youtube_url="https://youtube.com/watch?v=2"),
        ]

        downloader = BGMDownloader(config)

        # Mock download to always fail
        with patch.object(
            downloader,
            "download",
            side_effect=BGMDownloadError("Failed", "track", "url"),
        ):
            results = await downloader.ensure_all_downloaded(tracks)

        # Should return empty dict, not raise
        assert results == {}


class TestBGMSelector:
    """Test BGM selector."""

    @pytest.fixture
    def config(self) -> BGMConfig:
        """Create test config."""
        return BGMConfig(
            enabled=True,
            selection_mode="random",
            tracks=[
                BGMTrack(name="track1", youtube_url="https://youtube.com/1"),
                BGMTrack(name="track2", youtube_url="https://youtube.com/2"),
                BGMTrack(
                    name="track3",
                    youtube_url="https://youtube.com/3",
                    tags=["calm"],
                ),
            ],
        )

    def test_select_returns_none_when_empty(self, tmp_path: Path) -> None:
        """Test select returns None when no cached tracks."""
        config = BGMConfig(enabled=True)
        selector = BGMSelector(config, {})

        result = selector.select()

        assert result is None

    def test_select_random(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test random selection."""
        cached = {
            "track1": tmp_path / "track1.mp3",
            "track2": tmp_path / "track2.mp3",
        }
        selector = BGMSelector(config, cached)

        result = selector.select()

        assert result is not None
        track, path = result
        assert track.name in ["track1", "track2"]
        assert path in [tmp_path / "track1.mp3", tmp_path / "track2.mp3"]

    def test_select_sequential(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test sequential selection."""
        config.selection_mode = "sequential"
        cached = {
            "track1": tmp_path / "track1.mp3",
            "track2": tmp_path / "track2.mp3",
        }
        selector = BGMSelector(config, cached)

        # First selection
        result1 = selector.select()
        assert result1 is not None
        track1, _ = result1

        # Second selection should be different (or same if only 2 tracks)
        result2 = selector.select()
        assert result2 is not None
        track2, _ = result2

        # Third should cycle back
        result3 = selector.select()
        assert result3 is not None
        track3, _ = result3

        # Should have cycled through
        assert track3.name == track1.name

    def test_select_filters_by_tags(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test selection filters by tags when provided."""
        cached = {
            "track1": tmp_path / "track1.mp3",
            "track3": tmp_path / "track3.mp3",  # Has "calm" tag
        }
        selector = BGMSelector(config, cached)

        # Select with calm tag - should prefer track3
        result = selector.select(tags=["calm"])

        assert result is not None
        track, _ = result
        assert track.name == "track3"

    def test_select_only_returns_cached_tracks(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test selection only considers cached tracks."""
        # Only track2 is cached
        cached = {
            "track2": tmp_path / "track2.mp3",
        }
        selector = BGMSelector(config, cached)

        result = selector.select()

        assert result is not None
        track, _ = result
        assert track.name == "track2"


class TestBGMManager:
    """Test BGM manager."""

    @pytest.fixture
    def config(self, tmp_path: Path) -> BGMConfig:
        """Create test config."""
        return BGMConfig(
            enabled=True,
            cache_dir=str(tmp_path / "bgm"),
            tracks=[
                BGMTrack(name="track1", youtube_url="https://youtube.com/1"),
            ],
        )

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, tmp_path: Path) -> None:
        """Test manager returns None when BGM disabled."""
        config = BGMConfig(enabled=False, cache_dir=str(tmp_path / "bgm"))
        mock_downloader = MagicMock()
        manager = BGMManager(config, downloader=mock_downloader)

        path = await manager.get_bgm_for_video()

        assert path is None

    @pytest.mark.asyncio
    async def test_no_tracks_returns_none(self, tmp_path: Path) -> None:
        """Test manager returns None when no tracks configured."""
        config = BGMConfig(enabled=True, cache_dir=str(tmp_path))
        manager = BGMManager(config)

        path = await manager.get_bgm_for_video()

        assert path is None

    @pytest.mark.asyncio
    async def test_initialize_downloads_tracks(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test initialize downloads all tracks."""
        mock_downloader = MagicMock()
        mock_downloader.ensure_all_downloaded = AsyncMock(
            return_value={"track1": tmp_path / "track1.mp3"}
        )

        manager = BGMManager(config, downloader=mock_downloader)
        await manager.initialize()

        mock_downloader.ensure_all_downloaded.assert_called_once()
        assert manager._initialized is True
        assert manager.cached_track_count == 1

    @pytest.mark.asyncio
    async def test_lazy_initialization(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test lazy initialization on first get_bgm_for_video call."""
        mock_downloader = MagicMock()
        mock_downloader.ensure_all_downloaded = AsyncMock(
            return_value={"track1": tmp_path / "track1.mp3"}
        )

        manager = BGMManager(config, downloader=mock_downloader)

        # Should trigger lazy initialization
        await manager.get_bgm_for_video()

        mock_downloader.ensure_all_downloaded.assert_called_once()

    def test_is_enabled_property(self, config: BGMConfig, tmp_path: Path) -> None:
        """Test is_enabled property."""
        mock_downloader = MagicMock()
        manager = BGMManager(config, downloader=mock_downloader)
        assert manager.is_enabled is True

        disabled_config = BGMConfig(enabled=False, cache_dir=str(tmp_path / "bgm"))
        disabled_manager = BGMManager(disabled_config, downloader=mock_downloader)
        assert disabled_manager.is_enabled is False

    def test_get_volume(self, config: BGMConfig) -> None:
        """Test get_volume returns configured volume."""
        config.volume = 0.15
        mock_downloader = MagicMock()
        manager = BGMManager(config, downloader=mock_downloader)

        assert manager.get_volume() == 0.15

    def test_track_count_property(self, config: BGMConfig) -> None:
        """Test track_count property."""
        mock_downloader = MagicMock()
        manager = BGMManager(config, downloader=mock_downloader)
        assert manager.track_count == 1
