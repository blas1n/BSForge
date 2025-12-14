"""Base visual source interface and data structures.

This module defines the abstract base class for visual sources and
common data structures used across all visual implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class VisualSourceType(str, Enum):
    """Types of visual sources."""

    STOCK_VIDEO = "stock_video"
    STOCK_IMAGE = "stock_image"
    AI_IMAGE = "ai_image"
    SOLID_COLOR = "solid_color"
    GRADIENT = "gradient"


@dataclass
class VisualAsset:
    """Visual asset for video composition.

    Attributes:
        type: Type of visual source
        path: Local file path (after download)
        url: Remote URL (for downloading)
        duration: Duration in seconds (for videos, None for images)
        width: Asset width in pixels
        height: Asset height in pixels
        color: Hex color (for solid color)
        gradient_colors: List of hex colors (for gradient)
        source: Source identifier (e.g., "pexels", "dalle")
        source_id: ID from the source platform
        license: License information
        keywords: Keywords/tags associated with the asset
        metadata: Additional metadata
    """

    type: VisualSourceType
    path: Path | None = None
    url: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    color: str | None = None
    gradient_colors: list[str] | None = None
    source: str | None = None
    source_id: str | None = None
    license: str | None = None
    keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_video(self) -> bool:
        """Check if this asset is a video."""
        return self.type == VisualSourceType.STOCK_VIDEO

    @property
    def is_image(self) -> bool:
        """Check if this asset is an image."""
        return self.type in (
            VisualSourceType.STOCK_IMAGE,
            VisualSourceType.AI_IMAGE,
            VisualSourceType.SOLID_COLOR,
            VisualSourceType.GRADIENT,
        )

    @property
    def is_downloaded(self) -> bool:
        """Check if asset has been downloaded."""
        return self.path is not None and self.path.exists()


class BaseVisualSource(ABC):
    """Abstract base class for visual sources.

    All visual source implementations must inherit from this class
    and implement the required methods.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Search for visual assets.

        Args:
            query: Search query
            max_results: Maximum number of results
            orientation: Preferred orientation
            min_duration: Minimum duration for videos (seconds)

        Returns:
            List of matching visual assets
        """
        pass

    @abstractmethod
    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Download an asset to local storage.

        Args:
            asset: Asset to download
            output_dir: Directory to save the file

        Returns:
            Asset with updated path
        """
        pass


__all__ = [
    "VisualSourceType",
    "VisualAsset",
    "BaseVisualSource",
]
