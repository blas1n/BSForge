"""BGM Manager - orchestrates BGM download and selection.

Provides a single entry point for the video pipeline to get BGM.
"""

import logging
from pathlib import Path

from app.config.bgm import BGMConfig
from app.services.generator.bgm.downloader import BGMDownloader
from app.services.generator.bgm.selector import BGMSelector

logger = logging.getLogger(__name__)


class BGMManager:
    """Orchestrate BGM download, caching, and selection.

    Provides a simple interface for the video pipeline:
        1. Ensure tracks are downloaded on first use
        2. Select track for video generation
        3. Return path to audio file

    Example:
        >>> config = BGMConfig(enabled=True, tracks=[...])
        >>> manager = BGMManager(config)
        >>> await manager.initialize()
        >>> bgm_path = await manager.get_bgm_for_video()
        >>> # Pass bgm_path to compositor
    """

    def __init__(
        self,
        config: BGMConfig,
        downloader: BGMDownloader | None = None,
    ) -> None:
        """Initialize BGMManager.

        Args:
            config: BGM configuration.
            downloader: Optional BGMDownloader instance.
        """
        self.config = config
        self._downloader = downloader or BGMDownloader(config)
        self._cached_tracks: dict[str, Path] = {}
        self._selector: BGMSelector | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize manager by downloading all configured tracks.

        Should be called once at startup or on first use.
        Downloads are skipped if already cached.
        """
        if self._initialized:
            return

        if not self.config.enabled or not self.config.tracks:
            logger.info("BGM disabled or no tracks configured")
            self._initialized = True
            return

        logger.info(f"Initializing BGM: {len(self.config.tracks)} tracks configured")

        # Download all tracks
        self._cached_tracks = await self._downloader.ensure_all_downloaded(self.config.tracks)

        # Create selector with cached tracks
        self._selector = BGMSelector(self.config, self._cached_tracks)

        self._initialized = True
        logger.info(f"BGM initialized: {len(self._cached_tracks)} tracks cached")

    async def get_bgm_for_video(
        self,
        mood_tags: list[str] | None = None,
    ) -> Path | None:
        """Get BGM file path for video generation.

        Args:
            mood_tags: Optional mood tags for selection (future feature).

        Returns:
            Path to BGM audio file, or None if BGM disabled/unavailable.
        """
        if not self.config.enabled:
            return None

        # Lazy initialization
        if not self._initialized:
            await self.initialize()

        if not self._selector:
            return None

        result = self._selector.select(tags=mood_tags)
        if result:
            track, path = result
            return path

        return None

    def get_volume(self) -> float:
        """Get configured BGM volume.

        Returns:
            Volume level (0.0-1.0).
        """
        return self.config.volume

    @property
    def is_enabled(self) -> bool:
        """Check if BGM is enabled."""
        return self.config.enabled and len(self.config.tracks) > 0

    @property
    def track_count(self) -> int:
        """Get number of configured tracks."""
        return len(self.config.tracks)

    @property
    def cached_track_count(self) -> int:
        """Get number of cached tracks."""
        return len(self._cached_tracks)
