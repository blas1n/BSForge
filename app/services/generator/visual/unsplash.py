"""Free image sources.

Fetches free images from various APIs (no API key required).
"""

import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

logger = logging.getLogger(__name__)


class LoremFlickrSource(BaseVisualSource):
    """Fetch images from LoremFlickr.

    Uses loremflickr.com which provides random images from Flickr
    matching search keywords without API key.

    Example:
        >>> source = LoremFlickrSource()
        >>> assets = await source.search("technology computer", max_results=3)
        >>> downloaded = await source.download(assets[0], Path("/tmp"))
    """

    BASE_URL = "https://loremflickr.com"

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize LoremFlickrSource.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self._timeout = timeout

    async def search(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Create LoremFlickr image URLs.

        Args:
            query: Keywords to search for (comma-separated)
            max_results: Number of assets to return
            orientation: Image orientation
            min_duration: Ignored (images don't have duration)

        Returns:
            List of visual assets with LoremFlickr URLs
        """
        # Get dimensions based on orientation
        width, height = self._get_dimensions(orientation)

        # Clean query: replace spaces with commas for LoremFlickr
        clean_query = query.replace(" ", ",")

        assets: list[VisualAsset] = []
        for i in range(max_results):
            unique_id = uuid4().hex[:8]
            # LoremFlickr format: /width/height/keywords?lock=N (lock for consistent results)
            url = f"{self.BASE_URL}/{width}/{height}/{clean_query}?lock={i}"

            assets.append(
                VisualAsset(
                    type=VisualSourceType.STOCK_IMAGE,
                    url=url,
                    width=width,
                    height=height,
                    source="loremflickr",
                    source_id=f"flickr_{unique_id}",
                    license="Flickr (Creative Commons)",
                    keywords=query.split() if query else [],
                )
            )

        logger.info(f"Created {len(assets)} LoremFlickr image URLs for: {query}")
        return assets

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Download image from LoremFlickr.

        Args:
            asset: Asset with LoremFlickr URL
            output_dir: Directory to save the image

        Returns:
            Asset with updated local path
        """
        if not asset.url:
            raise ValueError("Asset has no URL")

        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{asset.source_id}.jpg"
        output_path = output_dir / filename

        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            response = await client.get(asset.url)
            response.raise_for_status()

            # Save image
            output_path.write_bytes(response.content)

        logger.info(f"Downloaded LoremFlickr image: {output_path}")
        asset.path = output_path
        return asset

    def _get_dimensions(
        self,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> tuple[int, int]:
        """Get dimensions for orientation.

        Args:
            orientation: Image orientation

        Returns:
            (width, height) tuple
        """
        if orientation == "portrait":
            return (1080, 1920)
        elif orientation == "landscape":
            return (1920, 1080)
        else:
            return (1080, 1080)


# Aliases for backwards compatibility
PicsumSource = LoremFlickrSource
UnsplashSource = LoremFlickrSource


__all__ = ["LoremFlickrSource", "PicsumSource", "UnsplashSource"]
