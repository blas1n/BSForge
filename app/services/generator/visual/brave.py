"""Brave Search Image API client for web image sourcing.

Brave Search provides web image search with a free tier (2,000 queries/month).
API documentation: https://brave.com/search/api/
"""

import logging
import os
from pathlib import Path
from typing import Any, Literal

import httpx

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

logger = logging.getLogger(__name__)

BRAVE_API_BASE = "https://api.search.brave.com/res/v1"


def _calculate_metadata_score(query: str, result: dict[str, Any]) -> float:
    """Calculate metadata matching score between query and result.

    Uses title, description, and source URL to determine relevance.
    Critical for celebrity image verification - checks if names appear in metadata.

    Args:
        query: Search query (e.g., "뉴진스 하니")
        result: API result dict with title, description, url

    Returns:
        Score between 0.0 and 1.0
    """
    query_tokens = set(query.lower().split())
    if not query_tokens:
        return 0.0

    score = 0.0

    # Get metadata fields
    title = (result.get("title") or "").lower()
    description = (result.get("description") or "").lower()
    source_url = (result.get("url") or "").lower()
    page_url = (result.get("page_url") or "").lower()

    # Score based on keyword presence
    for token in query_tokens:
        if len(token) < 2:  # Skip very short tokens
            continue

        if token in title:
            score += 0.4  # Title match is strongest signal
        if token in description:
            score += 0.3
        if token in source_url or token in page_url:
            score += 0.2

    return min(1.0, score)


class BraveImageClient(BaseVisualSource):
    """Brave Search Image API client for web image sourcing.

    Features:
    - Web image search (not just stock)
    - Free tier: 2,000 queries/month
    - Good for celebrity/news images

    Example:
        >>> client = BraveImageClient(api_key="your-key")
        >>> images = await client.search("뉴진스 하니", max_results=5)
        >>> downloaded = await client.download(images[0], Path("/tmp"))
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize BraveImageClient.

        Args:
            api_key: Brave Search API key (or from BRAVE_SEARCH_API_KEY env)
        """
        self._api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY")
        if not self._api_key:
            logger.warning("BRAVE_SEARCH_API_KEY not set, Brave search will not work")

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "X-Subscription-Token": self._api_key or "",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def search(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Search for images via Brave Search API.

        Args:
            query: Search query
            max_results: Maximum number of results
            orientation: Preferred orientation (used for filtering)
            min_duration: Not used (images only)

        Returns:
            List of image assets sorted by metadata_score
        """
        return await self.search_images(
            query=query,
            max_results=max_results,
            orientation=orientation,
        )

    async def search_images(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        country: str = "kr",
        search_lang: str = "ko",
    ) -> list[VisualAsset]:
        """Search for images via Brave Search API.

        Args:
            query: Search query (supports Korean)
            max_results: Maximum number of results
            orientation: Preferred orientation
            country: Country code for results
            search_lang: Search language

        Returns:
            List of image assets sorted by metadata_score
        """
        if not self._api_key:
            logger.warning("Brave API key not set")
            return []

        client = await self._get_client()

        params: dict[str, str | int] = {
            "q": query,
            "count": min(max_results * 2, 20),  # Request more for filtering
            "country": country,
            "search_lang": search_lang,
            "safesearch": "moderate",
        }

        try:
            response = await client.get(
                f"{BRAVE_API_BASE}/images/search",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Brave image search failed: {e}", exc_info=True)
            return []

        assets: list[VisualAsset] = []

        for result in data.get("results", []):
            # Get image properties
            properties = result.get("properties", {})
            thumbnail = result.get("thumbnail", {})

            # Get image URL (prefer source URL over thumbnail)
            image_url = properties.get("url") or thumbnail.get("src")
            if not image_url:
                continue

            # Get dimensions
            width = properties.get("width") or thumbnail.get("width") or 0
            height = properties.get("height") or thumbnail.get("height") or 0

            # Filter by orientation if dimensions available
            if width > 0 and height > 0:
                if orientation == "portrait" and width > height:
                    continue  # Skip landscape images when portrait wanted
                if orientation == "landscape" and height > width:
                    continue  # Skip portrait images when landscape wanted

            # Calculate metadata score for quality filtering
            meta_score = _calculate_metadata_score(query, result)

            assets.append(
                VisualAsset(
                    type=VisualSourceType.STOCK_IMAGE,
                    url=image_url,
                    width=width if width > 0 else None,
                    height=height if height > 0 else None,
                    source="brave",
                    source_id=f"brave_{hash(image_url) & 0xFFFFFFFF}",
                    license="Web Image",
                    keywords=query.split(),
                    metadata={
                        "title": result.get("title"),
                        "description": result.get("description"),
                        "page_url": result.get("url"),  # Page containing the image
                        "source_domain": result.get("source"),
                    },
                    metadata_score=meta_score,
                )
            )

        # Sort by metadata_score descending
        assets.sort(key=lambda a: a.metadata_score or 0.0, reverse=True)

        # Return top results
        assets = assets[:max_results]

        logger.info(
            f"Found {len(assets)} Brave images for query: {query} "
            f"(top score: {assets[0].metadata_score:.2f if assets else 0})"
        )
        return assets

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Download asset to local storage.

        Args:
            asset: Asset to download
            output_dir: Directory to save the file

        Returns:
            Asset with updated path

        Raises:
            ValueError: If asset has no URL
            RuntimeError: If download fails
        """
        if not asset.url:
            raise ValueError("Asset has no URL to download")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine file extension from URL or default to jpg
        ext = ".jpg"
        url_lower = asset.url.lower()
        if ".png" in url_lower:
            ext = ".png"
        elif ".gif" in url_lower:
            ext = ".gif"
        elif ".webp" in url_lower:
            ext = ".webp"

        filename = f"{asset.source_id}{ext}"
        output_path = output_dir / filename

        # Skip if already downloaded
        if output_path.exists():
            logger.debug(f"Asset already downloaded: {output_path}")
            asset.path = output_path
            return asset

        client = await self._get_client()

        try:
            # Download with custom headers to avoid blocks
            response = await client.get(
                asset.url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "image/*",
                },
                follow_redirects=True,
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded Brave image: {output_path}")
            asset.path = output_path
            return asset

        except httpx.HTTPError as e:
            raise RuntimeError(f"Download failed: {e}") from e

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = ["BraveImageClient"]
