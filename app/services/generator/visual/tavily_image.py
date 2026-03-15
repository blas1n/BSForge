"""Tavily image search client for visual sourcing.

Uses Tavily API's include_images feature to search for web images,
particularly useful for celebrity/person images not available on stock sites.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

from app.core.logging import get_logger
from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

if TYPE_CHECKING:
    from app.infrastructure.http_client import HTTPClient
    from app.services.research.tavily import TavilyClient

logger = get_logger(__name__)


class TavilyImageClient(BaseVisualSource):
    """Tavily-based web image search client.

    Uses Tavily API to search for images from the web.
    Useful for finding celebrity/person images that aren't
    available on stock photo sites.

    Attributes:
        tavily_client: TavilyClient instance for API calls
        http_client: HTTP client for downloading images
    """

    def __init__(
        self,
        tavily_client: TavilyClient,
        http_client: HTTPClient,
    ) -> None:
        """Initialize Tavily image client.

        Args:
            tavily_client: TavilyClient instance with search_images method
            http_client: HTTP client for downloading images
        """
        self._tavily = tavily_client
        self._http_client = http_client

    async def search(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Search for images using Tavily API.

        Args:
            query: Search query (e.g., "BTS Jungkook")
            max_results: Maximum number of results
            orientation: Ignored (Tavily doesn't filter by orientation)
            min_duration: Ignored (images only)

        Returns:
            List of VisualAsset objects with image URLs
        """
        try:
            image_urls = await self._tavily.search_images(query, max_results)

            assets = []
            for url in image_urls:
                # Extract filename from URL for source_id
                source_id = self._extract_filename(url)

                asset = VisualAsset(
                    type=VisualSourceType.STOCK_IMAGE,
                    url=url,
                    source="tavily_web",
                    source_id=source_id,
                    keywords=[query],
                    metadata={
                        "query": query,
                        "original_url": url,
                    },
                    # Tavily returns images directly matching the query
                    # so we trust the relevance (high metadata score)
                    metadata_score=1.0,
                )
                assets.append(asset)

            logger.info(f"Tavily image search for '{query}': {len(assets)} results")
            return assets

        except Exception as e:
            logger.error(f"Tavily image search failed: {e}")
            return []

    async def search_images(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[VisualAsset]:
        """Convenience method matching the visual source interface.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of VisualAsset objects
        """
        return await self.search(query, max_results)

    async def search_and_select_best(
        self,
        query: str,
        output_dir: Path,
        num_candidates: int = 10,
    ) -> VisualAsset | None:
        """Search images and select the best one.

        Downloads the first available candidate image.

        Args:
            query: Search query (e.g., "BTS Jungkook")
            output_dir: Directory to save the selected image
            num_candidates: Number of candidates to fetch

        Returns:
            Best matching VisualAsset, or None if no match found
        """
        assets = await self.search(query, max_results=num_candidates)
        if not assets:
            logger.warning(f"No images found for query: {query}")
            return None

        # Try downloading the first available asset
        for asset in assets:
            try:
                downloaded = await self.download(asset, output_dir)
                return downloaded
            except Exception as e:
                logger.warning(f"Failed to download candidate: {e}")
                continue

        return None

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Download an image from URL to local storage.

        Args:
            asset: Asset to download (must have url)
            output_dir: Directory to save the file

        Returns:
            Asset with updated path

        Raises:
            ValueError: If asset has no URL
        """
        if not asset.url:
            raise ValueError("Asset has no URL to download")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from URL or use UUID
        ext = self._get_extension(asset.url)
        filename = f"tavily_{uuid.uuid4().hex[:8]}{ext}"
        output_path = output_dir / filename

        try:
            response = await self._http_client.get(
                asset.url,
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                },
            )
            response.raise_for_status()

            # Write content to file
            output_path.write_bytes(response.content)

            # Update asset with local path
            asset.path = output_path
            logger.info(f"Downloaded Tavily image to {output_path}")
            return asset

        except Exception as e:
            logger.error(f"Failed to download Tavily image from {asset.url}: {e}")
            raise

    @staticmethod
    def _extract_filename(url: str) -> str:
        """Extract filename from URL.

        Args:
            url: Image URL

        Returns:
            Filename or URL hash if extraction fails
        """
        try:
            parsed = urlparse(url)
            path = parsed.path
            if path:
                return path.split("/")[-1]
            return uuid.uuid4().hex[:12]
        except Exception:
            return uuid.uuid4().hex[:12]

    @staticmethod
    def _get_extension(url: str) -> str:
        """Get file extension from URL.

        Args:
            url: Image URL

        Returns:
            File extension (e.g., ".jpg") or default ".jpg"
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                if path.endswith(ext):
                    return ext
            return ".jpg"  # Default
        except Exception:
            return ".jpg"


__all__ = ["TavilyImageClient"]
