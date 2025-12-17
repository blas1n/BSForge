"""BGM downloader using yt-dlp Python library.

Downloads audio from YouTube URLs and converts to MP3 format.
Handles caching to avoid re-downloads.
"""

import asyncio
import logging
from pathlib import Path

import yt_dlp

from app.config.bgm import BGMConfig, BGMTrack
from app.core.exceptions import BGMDownloadError

logger = logging.getLogger(__name__)


class BGMDownloader:
    """Download BGM tracks from YouTube using yt-dlp Python library.

    Features:
        - Automatic MP3 conversion
        - Skip if already cached
        - Configurable timeout

    Example:
        >>> config = BGMConfig(enabled=True, cache_dir="/data/bgm")
        >>> track = BGMTrack(name="test", youtube_url="https://youtube.com/...")
        >>> downloader = BGMDownloader(config)
        >>> path = await downloader.download(track)
    """

    def __init__(self, config: BGMConfig) -> None:
        """Initialize BGMDownloader.

        Args:
            config: BGM configuration with cache_dir and timeout.
        """
        self.config = config
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        cache_path = Path(self.config.cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)

    def _download_sync(self, track: BGMTrack, output_path: Path) -> Path:
        """Synchronous download using yt-dlp Python library.

        Args:
            track: BGMTrack with YouTube URL.
            output_path: Target output path.

        Returns:
            Path to downloaded MP3 file.

        Raises:
            BGMDownloadError: If download fails.
        """
        # Output template without extension (yt-dlp adds it)
        output_template = str(output_path.with_suffix("")) + ".%(ext)s"

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "extract_flat": False,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([str(track.youtube_url)])

            # Find the actual downloaded file
            return self._find_downloaded_file(output_path)

        except yt_dlp.DownloadError as e:
            raise BGMDownloadError(
                f"yt-dlp download failed: {e}",
                track_name=track.name,
                youtube_url=str(track.youtube_url),
            ) from e
        except Exception as e:
            raise BGMDownloadError(
                f"Download failed: {e}",
                track_name=track.name,
                youtube_url=str(track.youtube_url),
            ) from e

    async def download(self, track: BGMTrack) -> Path:
        """Download a BGM track from YouTube.

        Args:
            track: BGMTrack with YouTube URL.

        Returns:
            Path to downloaded MP3 file.

        Raises:
            BGMDownloadError: If download fails.
        """
        output_path = self.config.get_cache_path(track)

        # Skip if already cached
        if output_path.exists():
            logger.debug(f"BGM already cached: {track.name}")
            return output_path

        logger.info(f"Downloading BGM: {track.name} from {track.youtube_url}")

        try:
            # Run blocking yt-dlp in thread pool with timeout
            loop = asyncio.get_event_loop()
            actual_path = await asyncio.wait_for(
                loop.run_in_executor(None, self._download_sync, track, output_path),
                timeout=self.config.download_timeout,
            )

            logger.info(f"BGM downloaded: {track.name} -> {actual_path}")
            return actual_path

        except TimeoutError:
            raise BGMDownloadError(
                f"Download timeout after {self.config.download_timeout}s",
                track_name=track.name,
                youtube_url=str(track.youtube_url),
            ) from None
        except BGMDownloadError:
            raise
        except Exception as e:
            raise BGMDownloadError(
                f"Download failed: {e}",
                track_name=track.name,
                youtube_url=str(track.youtube_url),
            ) from e

    def _find_downloaded_file(self, expected_path: Path) -> Path:
        """Find the actual downloaded file.

        yt-dlp may add .mp3 extension even if already specified.

        Args:
            expected_path: Expected output path.

        Returns:
            Actual path to the downloaded file.

        Raises:
            BGMDownloadError: If file not found.
        """
        if expected_path.exists():
            return expected_path

        # Try with .mp3 extension
        mp3_path = expected_path.with_suffix(".mp3")
        if mp3_path.exists():
            return mp3_path

        # Search in cache dir for matching name
        cache_dir = Path(self.config.cache_dir)
        stem = expected_path.stem
        for file in cache_dir.glob(f"{stem}*"):
            if file.is_file() and file.suffix in (".mp3", ".m4a", ".opus", ".webm"):
                return file

        raise BGMDownloadError(
            f"Downloaded file not found: {expected_path}",
            track_name=str(expected_path),
            youtube_url="",
        )

    async def ensure_all_downloaded(self, tracks: list[BGMTrack]) -> dict[str, Path]:
        """Ensure all tracks are downloaded.

        Args:
            tracks: List of BGMTrack to download.

        Returns:
            Dict mapping track name to local path.
        """
        results: dict[str, Path] = {}

        for track in tracks:
            try:
                path = await self.download(track)
                results[track.name] = path
            except BGMDownloadError as e:
                logger.warning(f"Failed to download {track.name}: {e}")
                continue

        return results

    def is_cached(self, track: BGMTrack) -> bool:
        """Check if track is already cached.

        Args:
            track: BGMTrack to check.

        Returns:
            True if cached.
        """
        return self.config.get_cache_path(track).exists()
