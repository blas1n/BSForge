"""BGM (Background Music) service module.

This module provides BGM download, caching, and selection for video generation.

Components:
    - BGMDownloader: Downloads audio from YouTube using yt-dlp
    - BGMSelector: Selects BGM tracks based on configured mode (random/sequential)
    - BGMManager: Orchestrates download and selection

Example:
    >>> from app.config.bgm import BGMConfig, BGMTrack
    >>> from app.services.generator.bgm import BGMManager
    >>>
    >>> config = BGMConfig(
    ...     enabled=True,
    ...     cache_dir="/data/bgm",
    ...     tracks=[
    ...         BGMTrack(name="track1", youtube_url="https://youtube.com/..."),
    ...     ],
    ... )
    >>> manager = BGMManager(config)
    >>> await manager.initialize()
    >>> bgm_path = await manager.get_bgm_for_video()
"""

from app.services.generator.bgm.downloader import BGMDownloader
from app.services.generator.bgm.manager import BGMManager
from app.services.generator.bgm.selector import BGMSelector

__all__ = ["BGMDownloader", "BGMManager", "BGMSelector"]
