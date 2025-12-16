"""AI image generation using DALL-E 3.

Generates custom images for video backgrounds using OpenAI's DALL-E 3 model.
"""

import logging
import os
from pathlib import Path
from typing import Literal

import httpx

from app.config.video import AIImageConfig
from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

logger = logging.getLogger(__name__)


class AIImageGenerator(BaseVisualSource):
    """AI image generator using DALL-E 3.

    Features:
    - Custom image generation from prompts
    - Portrait format support for Shorts
    - Style customization

    Example:
        >>> generator = AIImageGenerator(api_key="your-key")
        >>> images = await generator.generate("futuristic city at night")
        >>> downloaded = await generator.download(images[0], Path("/tmp"))
    """

    def __init__(
        self,
        api_key: str | None = None,
        config: AIImageConfig | None = None,
    ) -> None:
        """Initialize AIImageGenerator.

        Args:
            api_key: OpenAI API key (or from OPENAI_API_KEY env)
            config: AI image configuration
        """
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            logger.warning("OPENAI_API_KEY not set, AI image generation will not work")

        self._config = config or AIImageConfig()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def search(
        self,
        query: str,
        max_results: int = 1,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Generate AI images based on query.

        Note: This generates new images, not searches existing ones.

        Args:
            query: Image description/prompt
            max_results: Number of images to generate
            orientation: Image orientation
            min_duration: Ignored for images

        Returns:
            List of generated image assets
        """
        return await self.generate(
            prompt=query,
            count=max_results,
            orientation=orientation,
        )

    async def generate(
        self,
        prompt: str,
        count: int = 1,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        style: str | None = None,
    ) -> list[VisualAsset]:
        """Generate images using DALL-E 3.

        Args:
            prompt: Image description
            count: Number of images to generate
            orientation: Image orientation
            style: Optional style override

        Returns:
            List of generated image assets
        """
        if not self._api_key:
            logger.warning("OpenAI API key not set")
            return []

        # Determine size based on orientation
        size = self._get_size_for_orientation(orientation)

        # Enhance prompt with style and quality hints
        enhanced_prompt = self._enhance_prompt(prompt, style)

        client = await self._get_client()
        assets: list[VisualAsset] = []

        # DALL-E 3 only supports n=1, so we loop
        for i in range(count):
            try:
                response = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    json={
                        "model": self._config.model,
                        "prompt": enhanced_prompt,
                        "n": 1,
                        "size": size,
                        "quality": self._config.quality,
                        "style": style or self._config.style,
                    },
                )
                response.raise_for_status()
                data = response.json()

                for image_data in data.get("data", []):
                    url = image_data.get("url")
                    if url:
                        # Parse size
                        width, height = map(int, size.split("x"))

                        assets.append(
                            VisualAsset(
                                type=VisualSourceType.AI_IMAGE,
                                url=url,
                                width=width,
                                height=height,
                                source="dalle",
                                source_id=f"dalle_{i}",
                                license="OpenAI Usage Policy",
                                keywords=prompt.split()[:5],
                                metadata={
                                    "prompt": prompt,
                                    "enhanced_prompt": enhanced_prompt,
                                    "revised_prompt": image_data.get("revised_prompt"),
                                    "model": self._config.model,
                                    "quality": self._config.quality,
                                    "style": style or self._config.style,
                                },
                            )
                        )

            except httpx.HTTPError as e:
                logger.error(f"DALL-E generation failed: {e}", exc_info=True)
                continue

        logger.info(f"Generated {len(assets)} AI images for prompt: {prompt[:50]}...")
        return assets

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Download generated image to local storage.

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

        filename = f"dalle_{asset.source_id}.png"
        output_path = output_dir / filename

        # DALL-E URLs expire, so always download fresh
        client = await self._get_client()

        try:
            response = await client.get(asset.url)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded AI image: {output_path}")
            asset.path = output_path
            return asset

        except httpx.HTTPError as e:
            raise RuntimeError(f"Download failed: {e}") from e

    def _get_size_for_orientation(
        self,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> str:
        """Get DALL-E size parameter for orientation.

        Args:
            orientation: Desired orientation

        Returns:
            Size string (e.g., "1024x1792")
        """
        if orientation == "portrait":
            return "1024x1792"
        elif orientation == "landscape":
            return "1792x1024"
        else:
            return "1024x1024"

    def _enhance_prompt(
        self,
        prompt: str,
        style: str | None = None,
    ) -> str:
        """Enhance prompt with quality and style hints.

        Args:
            prompt: Original prompt
            style: Optional style

        Returns:
            Enhanced prompt
        """
        enhancements = [
            "high quality",
            "detailed",
            "professional",
            "cinematic lighting",
        ]

        if style:
            enhancements.append(f"{style} style")

        # Add enhancements
        enhanced = f"{prompt}, {', '.join(enhancements)}"

        # Add format hint for Shorts
        enhanced += ", vertical format, suitable for mobile viewing"

        return enhanced

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = ["AIImageGenerator"]
