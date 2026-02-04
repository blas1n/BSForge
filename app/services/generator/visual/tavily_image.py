"""Tavily image search client for visual sourcing.

Uses Tavily API's include_images feature to search for web images,
particularly useful for celebrity/person images not available on stock sites.

Includes CLIP-based image verification to select the most relevant image
from search results by comparing similarity scores.
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

if TYPE_CHECKING:
    from app.infrastructure.http_client import HTTPClient
    from app.services.generator.visual.stable_diffusion import StableDiffusionGenerator
    from app.services.research.tavily import TavilyClient

logger = logging.getLogger(__name__)


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
        sd_generator: StableDiffusionGenerator | None = None,
    ) -> None:
        """Initialize Tavily image client.

        Args:
            tavily_client: TavilyClient instance with search_images method
            http_client: HTTP client for downloading images
            sd_generator: Optional SD generator for CLIP evaluation
        """
        self._tavily = tavily_client
        self._http_client = http_client
        self._sd_generator = sd_generator

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
        min_clip_score: float = 0.2,
    ) -> VisualAsset | None:
        """Search images and select the best one using CLIP verification.

        Downloads multiple candidate images, evaluates each with CLIP,
        and returns the one with the highest similarity score to the query.

        This helps verify that web-searched images (e.g., celebrity photos)
        actually match the search query.

        Args:
            query: Search query (e.g., "니키미나즈", "BTS Jungkook")
            output_dir: Directory to save the selected image
            num_candidates: Number of images to evaluate (default 10)
            min_clip_score: Minimum CLIP score to accept (default 0.2)

        Returns:
            Best matching VisualAsset, or None if no good match found
        """
        if not self._sd_generator:
            logger.warning("SD generator not available, using first result")
            assets = await self.search(query, max_results=1)
            if assets:
                return await self.download(assets[0], output_dir)
            return None

        # Search for candidates
        assets = await self.search(query, max_results=num_candidates)
        if not assets:
            logger.warning(f"No images found for query: {query}")
            return None

        logger.info(f"Evaluating {len(assets)} candidate images for '{query}'")

        # Download to temp dir and evaluate with CLIP
        best_asset: VisualAsset | None = None
        best_score: float = 0.0
        temp_dir = Path(tempfile.mkdtemp(prefix="tavily_clip_"))

        try:
            for i, asset in enumerate(assets):
                try:
                    # Download to temp location
                    temp_asset = await self._download_to_temp(asset, temp_dir, i)
                    if not temp_asset.path:
                        continue

                    # Evaluate with CLIP
                    score = await self._sd_generator.evaluate(temp_asset.path, query)
                    if score is None:
                        continue

                    url_preview = (asset.url or "")[:50]
                    logger.info(
                        f"  [{i+1}/{len(assets)}] CLIP score: {score:.3f} "
                        f"(url: {url_preview}...)"
                    )

                    if score > best_score:
                        best_score = score
                        best_asset = temp_asset

                except Exception as e:
                    logger.warning(f"Failed to evaluate image {i}: {e}")
                    continue

            # Check if best score meets threshold
            if best_asset and best_asset.path and best_score >= min_clip_score:
                logger.info(f"Selected best image with CLIP score {best_score:.3f} for '{query}'")
                # Move to final output directory
                output_dir.mkdir(parents=True, exist_ok=True)
                final_path = output_dir / best_asset.path.name
                best_asset.path.rename(final_path)
                best_asset.path = final_path
                best_asset.metadata["clip_score"] = best_score
                best_asset.metadata_score = best_score

                # Upscale if image is too small (target: 1080x1920 for Shorts)
                best_asset = await self._upscale_if_needed(
                    best_asset, query, min_width=720, min_height=1280
                )

                return best_asset
            else:
                logger.warning(
                    f"No image met min CLIP threshold {min_clip_score} " f"(best: {best_score:.3f})"
                )
                return None

        finally:
            # Cleanup temp files
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _download_to_temp(
        self,
        asset: VisualAsset,
        temp_dir: Path,
        index: int,
    ) -> VisualAsset:
        """Download image to temporary directory.

        Args:
            asset: Asset to download
            temp_dir: Temporary directory
            index: Index for unique filename

        Returns:
            Asset with updated path

        Raises:
            ValueError: If downloaded content is not a valid image
        """
        url = asset.url or ""
        response = await self._http_client.get(
            url,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            },
        )
        response.raise_for_status()
        content = response.content

        # Validate image format by magic bytes
        ext = self._detect_image_format(content)
        if ext is None:
            raise ValueError(f"Invalid image format from {url[:50]}...")

        filename = f"candidate_{index:02d}{ext}"
        output_path = temp_dir / filename
        output_path.write_bytes(content)

        asset.path = output_path
        return asset

    @staticmethod
    def _detect_image_format(content: bytes) -> str | None:
        """Detect image format from magic bytes.

        Args:
            content: File content

        Returns:
            File extension (.jpg, .png, etc.) or None if not a valid image
        """
        if len(content) < 10:
            return None

        # JPEG: FF D8 FF
        if content[:3] == b"\xff\xd8\xff":
            return ".jpg"
        # PNG: 89 50 4E 47
        if content[:4] == b"\x89PNG":
            return ".png"
        # GIF: GIF87a or GIF89a
        if content[:4] == b"GIF8":
            return ".gif"
        # WebP: RIFF....WEBP
        if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return ".webp"

        # Check if it's HTML (error page)
        if b"<html" in content[:500].lower() or b"<!doctype" in content[:500].lower():
            return None

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

    async def _upscale_if_needed(
        self,
        asset: VisualAsset,
        prompt: str,
        min_width: int = 720,
        min_height: int = 1280,
    ) -> VisualAsset:
        """Upscale image using Real-ESRGAN if resolution is too low.

        Args:
            asset: Asset with path to image
            prompt: Prompt (unused, kept for API compatibility)
            min_width: Minimum acceptable width
            min_height: Minimum acceptable height

        Returns:
            Asset with upscaled image path (or original if large enough)
        """
        if not asset.path or not self._sd_generator:
            return asset

        try:
            from PIL import Image

            with Image.open(asset.path) as img:
                width, height = img.size

            if width >= min_width and height >= min_height:
                logger.info(f"  Image size OK: {width}x{height}")
                return asset

            # Calculate scale factor needed
            scale_w = min_width / width
            scale_h = min_height / height
            scale = max(2, min(4, int(max(scale_w, scale_h) + 0.5)))

            logger.info(
                f"  [UPSCALE] Image too small ({width}x{height}), "
                f"upscaling {scale}x with Real-ESRGAN..."
            )

            # Use Real-ESRGAN for high quality upscaling
            upscaled_path = await self._sd_generator.upscale(
                source_image=asset.path,
                output_dir=asset.path.parent,
                scale=scale,
            )

            if upscaled_path and upscaled_path.exists():
                asset.path = upscaled_path
                asset.metadata["upscaled"] = True
                asset.metadata["original_size"] = f"{width}x{height}"
                asset.metadata["upscale_method"] = "realesrgan"
                logger.info(f"  [UPSCALE] Success: {upscaled_path}")

        except Exception as e:
            logger.warning(f"  [UPSCALE] Failed, using original: {e}")

        return asset


__all__ = ["TavilyImageClient"]
