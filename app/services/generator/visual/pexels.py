"""Pexels API client for stock video and image sourcing.

Pexels provides free stock videos and images with attribution.
API documentation: https://www.pexels.com/api/documentation/
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

PEXELS_API_BASE = "https://api.pexels.com"


def _calculate_metadata_score(query: str, result: dict[str, Any]) -> float:
    """Calculate metadata matching score between query and result.

    Uses title, description, and keywords to determine relevance.
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

    # Get URL (often contains descriptive text like "pexels-photo-1234-mountain-sunset")
    url = result.get("url", "")
    if url:
        # Extract meaningful parts from URL
        parts = url.replace("-", " ").replace("_", " ").lower()
        metadata_text.append(parts)

    # Get photographer (can be indicative of theme)
    photographer = result.get("user", {}).get("name", "") or result.get("photographer", "")
    if photographer:
        metadata_text.append(photographer.lower())

    # Get alt text (Pexels images have this)
    alt = result.get("alt", "")
    if alt:
        metadata_text.append(alt.lower())

    # Combine all metadata
    full_text = " ".join(metadata_text)
    if not full_text.strip():
        # No metadata available, return neutral score
        return 0.5

    # Calculate token overlap
    text_tokens = set(full_text.split())
    matches = query_tokens & text_tokens

    # Score = matched tokens / query tokens
    score = len(matches) / len(query_tokens)

    return min(1.0, score)


class PexelsClient(BaseVisualSource):
    """Pexels API client for stock video and image sourcing.

    Features:
    - Free high-quality stock videos and images
    - Portrait orientation support (perfect for Shorts)
    - No attribution required in video (only in description)

    Example:
        >>> client = PexelsClient(api_key="your-key")
        >>> videos = await client.search_videos("technology", max_results=5)
        >>> downloaded = await client.download(videos[0], Path("/tmp"))
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize PexelsClient.

        Args:
            api_key: Pexels API key (or from PEXELS_API_KEY env)
        """
        self._api_key = api_key or os.environ.get("PEXELS_API_KEY")
        if not self._api_key:
            logger.warning("PEXELS_API_KEY not set, Pexels search will not work")

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Authorization": self._api_key or ""},
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
            logger.warning(f"Video search failed: {e}")

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
                logger.warning(f"Image search failed: {e}")

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
            orientation: Video orientation
            min_duration: Minimum duration in seconds

        Returns:
            List of video assets
        """
        if not self._api_key:
            logger.warning("Pexels API key not set")
            return []

        client = await self._get_client()

        params: dict[str, str | int] = {
            "query": query,
            "per_page": min(max_results * 2, 80),  # Request more for filtering
            "orientation": orientation,
        }

        try:
            response = await client.get(
                f"{PEXELS_API_BASE}/videos/search",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Pexels video search failed: {e}", exc_info=True)
            return []

        assets: list[VisualAsset] = []

        for video in data.get("videos", []):
            duration = video.get("duration", 0)

            # Filter by min_duration
            if min_duration and duration < min_duration:
                continue

            # Find best video file (HD, portrait)
            video_file = self._select_best_video_file(
                video.get("video_files", []),
                orientation,
            )

            if not video_file:
                continue

            assets.append(
                VisualAsset(
                    type=VisualSourceType.STOCK_VIDEO,
                    url=video_file.get("link"),
                    duration=duration,
                    width=video_file.get("width"),
                    height=video_file.get("height"),
                    source="pexels",
                    source_id=str(video.get("id")),
                    license="Pexels License",
                    keywords=query.split(),
                    metadata={
                        "photographer": video.get("user", {}).get("name"),
                        "pexels_url": video.get("url"),
                    },
                    metadata_score=_calculate_metadata_score(query, video),
                )
            )

            if len(assets) >= max_results:
                break

        logger.info(f"Found {len(assets)} Pexels videos for query: {query}")
        return assets

    async def search_images(
        self,
        query: str,
        max_results: int = 10,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        exclude_ids: set[str] | None = None,
    ) -> list[VisualAsset]:
        """Search for stock images.

        Args:
            query: Search query
            max_results: Maximum number of results
            orientation: Image orientation
            exclude_ids: Set of source_ids to exclude (to avoid duplicates)

        Returns:
            List of image assets
        """
        if not self._api_key:
            logger.warning("Pexels API key not set")
            return []

        client = await self._get_client()

        # Request more results to have room for filtering out excluded IDs
        request_count = max_results + (len(exclude_ids) if exclude_ids else 0) + 5

        params: dict[str, str | int] = {
            "query": query,
            "per_page": min(request_count, 80),
            "orientation": orientation,
        }

        try:
            response = await client.get(
                f"{PEXELS_API_BASE}/v1/search",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Pexels image search failed: {e}", exc_info=True)
            return []

        assets: list[VisualAsset] = []

        for photo in data.get("photos", []):
            photo_id = str(photo.get("id"))

            # Skip if this ID is in the exclude list
            if exclude_ids and photo_id in exclude_ids:
                logger.debug(f"Skipping excluded image ID: {photo_id}")
                continue

            # Use large2x size for quality
            src = photo.get("src", {})
            url = src.get("large2x") or src.get("large") or src.get("original")

            if not url:
                continue

            assets.append(
                VisualAsset(
                    type=VisualSourceType.STOCK_IMAGE,
                    url=url,
                    width=photo.get("width"),
                    height=photo.get("height"),
                    source="pexels",
                    source_id=str(photo.get("id")),
                    license="Pexels License",
                    keywords=query.split(),
                    metadata={
                        "photographer": photo.get("photographer"),
                        "pexels_url": photo.get("url"),
                        "avg_color": photo.get("avg_color"),
                    },
                    metadata_score=_calculate_metadata_score(query, photo),
                )
            )

            # Stop once we have enough
            if len(assets) >= max_results:
                break

        logger.info(f"Found {len(assets)} Pexels images for query: {query}")
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

        filename = f"pexels_{asset.source_id}{ext}"
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

    def _select_best_video_file(
        self,
        video_files: list[dict[str, Any]],
        orientation: str,
    ) -> dict[str, Any] | None:
        """Select best video file based on quality and orientation.

        Args:
            video_files: List of video file options
            orientation: Preferred orientation

        Returns:
            Best video file dict or None
        """
        if not video_files:
            return None

        # Filter by orientation
        if orientation == "portrait":
            # Portrait: width < height
            files = [f for f in video_files if f.get("width", 0) < f.get("height", 0)]
        elif orientation == "landscape":
            files = [f for f in video_files if f.get("width", 0) > f.get("height", 0)]
        else:
            files = video_files

        if not files:
            files = video_files  # Fallback to all files

        # Sort by quality (prefer HD)
        def quality_score(f: dict[str, Any]) -> int:
            quality_val = f.get("quality", "")
            quality = str(quality_val).lower()
            if quality == "hd":
                return 3
            if quality == "sd":
                return 2
            return 1

        files.sort(key=quality_score, reverse=True)
        return files[0]

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = ["PexelsClient"]
