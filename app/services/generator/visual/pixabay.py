"""Pixabay API client for stock video and image sourcing.

Pixabay provides free stock videos and images without attribution requirement.
API documentation: https://pixabay.com/api/docs/
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

PIXABAY_API_BASE = "https://pixabay.com/api"


def _calculate_metadata_score(query: str, result: dict[str, Any]) -> float:
    """Calculate metadata matching score between query and result.

    Uses tags and page URL to determine relevance.
    Score is based on keyword token overlap.

    Args:
        query: Search query
        result: API result dict with potential metadata

    Returns:
        Score between 0.0 and 1.0
    """
    # Normalize query tokens
    query_tokens = set(query.lower().split())
    if not query_tokens:
        return 0.0

    # Gather metadata text
    metadata_text = []

    # Get tags (Pixabay provides comma-separated tags)
    tags = result.get("tags", "")
    if tags:
        metadata_text.append(tags.lower())

    # Get page URL (contains descriptive slug)
    page_url = result.get("pageURL", "")
    if page_url:
        # Extract meaningful parts from URL
        parts = page_url.replace("-", " ").replace("_", " ").replace("/", " ").lower()
        metadata_text.append(parts)

    # Get user (sometimes indicative of theme)
    user = result.get("user", "")
    if user:
        metadata_text.append(user.lower())

    # Combine all metadata
    full_text = " ".join(metadata_text)
    if not full_text.strip():
        # No metadata available, return neutral score
        return 0.5

    # Calculate token overlap
    text_tokens = set(full_text.replace(",", " ").split())
    matches = query_tokens & text_tokens

    # Score = matched tokens / query tokens
    score = len(matches) / len(query_tokens)

    return min(1.0, score)


class PixabayClient(BaseVisualSource):
    """Pixabay API client for stock video and image sourcing.

    Features:
    - Free high-quality stock videos and images
    - No attribution required (Pixabay License)
    - Portrait orientation support for Shorts
    - 100 requests per minute rate limit

    Example:
        >>> client = PixabayClient(api_key="your-key")
        >>> videos = await client.search_videos("technology", max_results=5)
        >>> downloaded = await client.download(videos[0], Path("/tmp"))
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize PixabayClient.

        Args:
            api_key: Pixabay API key (or from PIXABAY_API_KEY env)
        """
        self._api_key = api_key or os.environ.get("PIXABAY_API_KEY")
        if not self._api_key:
            logger.warning("PIXABAY_API_KEY not set, Pixabay search will not work")

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def search(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Search for videos (primary) and images (fallback).

        Args:
            query: Search query
            max_results: Maximum number of results
            orientation: Preferred orientation
            min_duration: Minimum duration for videos

        Returns:
            List of visual assets (videos first, then images)
        """
        assets: list[VisualAsset] = []

        # Search videos first
        try:
            videos = await self.search_videos(
                query=query,
                max_results=max_results,
                orientation=orientation,
                min_duration=min_duration,
            )
            assets.extend(videos)
        except Exception as e:
            logger.warning(f"Pixabay video search failed: {e}")

        # If not enough videos, search images
        if len(assets) < max_results:
            try:
                images = await self.search_images(
                    query=query,
                    max_results=max_results - len(assets),
                    orientation=orientation,
                )
                assets.extend(images)
            except Exception as e:
                logger.warning(f"Pixabay image search failed: {e}")

        return assets

    async def search_videos(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Search for stock videos.

        Args:
            query: Search query
            max_results: Maximum number of results
            orientation: Video orientation (horizontal, vertical, or all)
            min_duration: Minimum duration in seconds

        Returns:
            List of video assets
        """
        if not self._api_key:
            logger.warning("Pixabay API key not set")
            return []

        client = await self._get_client()

        # Map orientation to Pixabay's parameter
        pixabay_orientation = self._map_orientation(orientation)

        params: dict[str, str | int] = {
            "key": self._api_key,
            "q": query,
            "per_page": min(max_results * 2, 200),  # Request more for filtering
            "video_type": "all",
            "safesearch": "true",
        }

        if pixabay_orientation != "all":
            params["orientation"] = pixabay_orientation

        try:
            response = await client.get(
                f"{PIXABAY_API_BASE}/videos/",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Pixabay video API error: {e.response.status_code} - " f"{e.response.text[:500]}"
            )
            return []
        except httpx.HTTPError as e:
            logger.error(f"Pixabay video search failed: {e}", exc_info=True)
            return []

        assets: list[VisualAsset] = []

        for video in data.get("hits", []):
            duration = video.get("duration", 0)

            # Filter by min_duration
            if min_duration and duration < min_duration:
                continue

            # Get best video URL (prefer large, then medium, then small)
            video_url = self._select_best_video_url(video.get("videos", {}))

            if not video_url:
                continue

            # Get video dimensions
            video_info = self._get_video_info(video.get("videos", {}))

            assets.append(
                VisualAsset(
                    type=VisualSourceType.STOCK_VIDEO,
                    url=video_url,
                    duration=duration,
                    width=video_info.get("width"),
                    height=video_info.get("height"),
                    source="pixabay",
                    source_id=str(video.get("id")),
                    license="Pixabay License",
                    keywords=video.get("tags", "").split(", "),
                    metadata={
                        "user": video.get("user"),
                        "pixabay_url": video.get("pageURL"),
                        "views": video.get("views"),
                        "downloads": video.get("downloads"),
                    },
                    metadata_score=_calculate_metadata_score(query, video),
                )
            )

            if len(assets) >= max_results:
                break

        logger.info(f"Found {len(assets)} Pixabay videos for query: {query}")
        return assets

    async def search_images(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        image_type: Literal["all", "photo", "illustration", "vector"] = "photo",
    ) -> list[VisualAsset]:
        """Search for stock images.

        Args:
            query: Search query
            max_results: Maximum number of results
            orientation: Image orientation
            image_type: Type of image (photo, illustration, vector)

        Returns:
            List of image assets
        """
        if not self._api_key:
            logger.warning("Pixabay API key not set")
            return []

        client = await self._get_client()

        # Map orientation to Pixabay's parameter
        pixabay_orientation = self._map_orientation(orientation)

        params: dict[str, str | int] = {
            "key": self._api_key,
            "q": query,
            "per_page": min(max_results + 5, 200),
            "image_type": image_type,
            "safesearch": "true",
        }

        if pixabay_orientation != "all":
            params["orientation"] = pixabay_orientation

        try:
            response = await client.get(
                f"{PIXABAY_API_BASE}/",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Pixabay image API error: {e.response.status_code} - " f"{e.response.text[:500]}"
            )
            return []
        except httpx.HTTPError as e:
            logger.error(f"Pixabay image search failed: {e}", exc_info=True)
            return []

        assets: list[VisualAsset] = []

        for photo in data.get("hits", []):
            # Use largeImageURL for quality (1280px)
            url = photo.get("largeImageURL") or photo.get("webformatURL")

            if not url:
                continue

            assets.append(
                VisualAsset(
                    type=VisualSourceType.STOCK_IMAGE,
                    url=url,
                    width=photo.get("imageWidth"),
                    height=photo.get("imageHeight"),
                    source="pixabay",
                    source_id=str(photo.get("id")),
                    license="Pixabay License",
                    keywords=photo.get("tags", "").split(", "),
                    metadata={
                        "user": photo.get("user"),
                        "pixabay_url": photo.get("pageURL"),
                        "views": photo.get("views"),
                        "downloads": photo.get("downloads"),
                    },
                    metadata_score=_calculate_metadata_score(query, photo),
                )
            )

            if len(assets) >= max_results:
                break

        logger.info(f"Found {len(assets)} Pixabay images for query: {query}")
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

        # Determine file extension
        ext = ".mp4" if asset.is_video else ".jpg"

        filename = f"pixabay_{asset.source_id}{ext}"
        output_path = output_dir / filename

        # Skip if already downloaded
        if output_path.exists():
            logger.debug(f"Asset already downloaded: {output_path}")
            asset.path = output_path
            return asset

        client = await self._get_client()

        try:
            async with client.stream("GET", asset.url) as response:
                response.raise_for_status()

                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

            logger.info(f"Downloaded: {output_path}")
            asset.path = output_path
            return asset

        except httpx.HTTPError as e:
            raise RuntimeError(f"Download failed: {e}") from e

    def _map_orientation(
        self,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> str:
        """Map orientation to Pixabay's parameter.

        Pixabay uses: horizontal, vertical, all

        Args:
            orientation: Our orientation value

        Returns:
            Pixabay orientation parameter
        """
        mapping = {
            "portrait": "vertical",
            "landscape": "horizontal",
            "square": "all",  # Pixabay doesn't have square filter
        }
        return mapping.get(orientation, "all")

    def _select_best_video_url(self, videos: dict[str, Any]) -> str | None:
        """Select best video URL from Pixabay video sizes.

        Pixabay provides: large (1920), medium (1280), small (960), tiny (640)

        Args:
            videos: Video sizes dict from Pixabay API

        Returns:
            Best video URL or None
        """
        # Prefer large for quality, but medium is usually sufficient
        for size in ["large", "medium", "small", "tiny"]:
            if size in videos and videos[size].get("url"):
                url = videos[size]["url"]
                if isinstance(url, str):
                    return url
        return None

    def _get_video_info(self, videos: dict[str, Any]) -> dict[str, int]:
        """Get video dimensions from the best available size.

        Args:
            videos: Video sizes dict from Pixabay API

        Returns:
            Dict with width and height
        """
        for size in ["large", "medium", "small", "tiny"]:
            if size in videos:
                return {
                    "width": videos[size].get("width", 0),
                    "height": videos[size].get("height", 0),
                }
        return {"width": 0, "height": 0}

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = ["PixabayClient"]
