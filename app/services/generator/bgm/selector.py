"""BGM track selector.

Selects BGM tracks based on configured selection mode.
"""

import logging
import random
from pathlib import Path

from app.config.bgm import BGMConfig, BGMTrack

logger = logging.getLogger(__name__)


class BGMSelector:
    """Select BGM tracks for video generation.

    Supports multiple selection modes:
        - random: Random selection from available tracks
        - sequential: Round-robin through tracks

    Example:
        >>> config = BGMConfig(enabled=True, selection_mode="random", tracks=[...])
        >>> cached_tracks = {"track1": Path("/data/bgm/track1.mp3")}
        >>> selector = BGMSelector(config, cached_tracks)
        >>> track, path = selector.select()
    """

    def __init__(
        self,
        config: BGMConfig,
        cached_tracks: dict[str, Path],
    ) -> None:
        """Initialize BGMSelector.

        Args:
            config: BGM configuration.
            cached_tracks: Dict mapping track name to local path.
        """
        self.config = config
        self.cached_tracks = cached_tracks
        self._sequential_index = 0

    def select(
        self,
        tags: list[str] | None = None,
    ) -> tuple[BGMTrack, Path] | None:
        """Select a BGM track.

        Args:
            tags: Optional mood tags for filtering (future feature).

        Returns:
            Tuple of (BGMTrack, Path) or None if no tracks available.
        """
        if not self.cached_tracks:
            logger.warning("No BGM tracks available")
            return None

        # Get available tracks (those with cached files)
        available_tracks = [t for t in self.config.tracks if t.name in self.cached_tracks]

        if not available_tracks:
            logger.warning("No cached BGM tracks")
            return None

        # Filter by tags if provided (future feature)
        if tags:
            matching_tracks = [t for t in available_tracks if any(tag in t.tags for tag in tags)]
            if matching_tracks:
                available_tracks = matching_tracks

        # Select based on mode
        if self.config.selection_mode == "random":
            track = self._select_random(available_tracks)
        elif self.config.selection_mode == "sequential":
            track = self._select_sequential(available_tracks)
        else:
            track = self._select_random(available_tracks)

        if track:
            path = self.cached_tracks[track.name]
            logger.info(f"Selected BGM: {track.name}")
            return track, path

        return None

    def _select_random(self, tracks: list[BGMTrack]) -> BGMTrack | None:
        """Random selection.

        Args:
            tracks: Available tracks.

        Returns:
            Randomly selected track or None.
        """
        if not tracks:
            return None
        return random.choice(tracks)

    def _select_sequential(self, tracks: list[BGMTrack]) -> BGMTrack | None:
        """Sequential (round-robin) selection.

        Args:
            tracks: Available tracks.

        Returns:
            Next track in sequence or None.
        """
        if not tracks:
            return None

        track = tracks[self._sequential_index % len(tracks)]
        self._sequential_index += 1
        return track
