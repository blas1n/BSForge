"""Background music configuration models.

This module defines Pydantic models for BGM configuration used in video generation.
BGM tracks are sourced from YouTube Audio Library and cached locally.
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class BGMTrack(BaseModel):
    """Single BGM track configuration.

    Attributes:
        name: Human-readable track name for identification and cache filename.
        youtube_url: YouTube Audio Library URL.
        tags: Optional tags for mood-based selection (future feature).
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Track identifier (used for cache filename)",
    )
    youtube_url: HttpUrl = Field(..., description="YouTube URL for audio source")
    tags: list[str] = Field(default_factory=list, description="Mood/style tags")


class BGMConfig(BaseModel):
    """BGM configuration for a channel.

    Attributes:
        enabled: Whether BGM is enabled for this channel.
        tracks: List of available BGM tracks.
        volume: Default playback volume (0.0-1.0).
        cache_dir: Path for caching downloaded BGM files.
        selection_mode: How to select tracks ("random" or "sequential").
        download_timeout: Timeout for yt-dlp downloads in seconds.
    """

    enabled: bool = Field(default=False, description="Enable BGM")
    tracks: list[BGMTrack] = Field(default_factory=list, description="Available tracks")
    volume: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="BGM volume (0.0-1.0)",
    )
    cache_dir: str = Field(
        default="data/bgm",
        description="Path for caching downloaded BGM files",
    )
    selection_mode: str = Field(
        default="random",
        pattern=r"^(random|sequential)$",
        description="Track selection mode",
    )
    download_timeout: int = Field(
        default=300,
        ge=30,
        le=600,
        description="yt-dlp timeout in seconds",
    )

    def get_cache_path(self, track: BGMTrack) -> Path:
        """Get cache path for a track.

        Uses sanitized track name as filename.

        Args:
            track: BGM track to get cache path for.

        Returns:
            Path to the cached audio file.
        """
        safe_name = re.sub(r"[^\w\-]", "_", track.name)
        return Path(self.cache_dir) / f"{safe_name}.mp3"
