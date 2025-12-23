"""Stable Diffusion HTTP client for image generation.

Communicates with the SD Docker service via HTTP API.
Provides graceful fallback when SD service is unavailable.
"""

import base64
import logging
from pathlib import Path
from typing import Literal

import httpx

from app.config.video import StableDiffusionConfig
from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

logger = logging.getLogger(__name__)


class StableDiffusionGenerator(BaseVisualSource):
    """Stable Diffusion HTTP client.

    Communicates with the SD service running in a separate Docker container.
    Provides graceful fallback when the service is unavailable.

    Features:
    - HTTP API communication with SD service
    - Automatic device detection (CUDA/MPS/CPU)
    - Graceful fallback when service unavailable
    - Base64 image transfer

    Example:
        >>> config = StableDiffusionConfig()
        >>> generator = StableDiffusionGenerator(config)
        >>> if await generator.is_available():
        ...     images = await generator.generate("sunset over mountains")
        ...     downloaded = await generator.download(images[0], Path("/tmp"))
    """

    def __init__(self, config: StableDiffusionConfig | None = None) -> None:
        """Initialize StableDiffusionGenerator.

        Args:
            config: SD service configuration
        """
        self._config = config or StableDiffusionConfig()
        self._client: httpx.AsyncClient | None = None
        self._service_available: bool | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._config.timeout, connect=10.0)
            )
        return self._client

    async def is_available(self) -> bool:
        """Check if SD service is available.

        Returns:
            True if service is healthy and responding
        """
        if not self._config.enabled:
            return False

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self._config.service_url}/health",
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                self._service_available = data.get("status") == "ok"
                logger.info(
                    f"SD service available: device={data.get('device')}, "
                    f"model_loaded={data.get('model_loaded')}"
                )
                return self._service_available

        except httpx.HTTPError as e:
            logger.warning(f"SD service unavailable: {e}")
        except Exception as e:
            logger.warning(f"SD service check failed: {e}")

        self._service_available = False
        return False

    async def search(
        self,
        query: str,
        max_results: int = 1,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Generate images based on query (implements BaseVisualSource).

        Args:
            query: Image description prompt
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
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> list[VisualAsset]:
        """Generate images using Stable Diffusion.

        Args:
            prompt: Image description
            count: Number of images to generate
            orientation: Image orientation
            negative_prompt: Negative prompt override
            seed: Random seed for reproducibility

        Returns:
            List of generated image assets (with base64 data)
        """
        if not self._config.enabled:
            logger.warning("SD generation disabled in config")
            return []

        # Check service availability
        if self._service_available is None:
            await self.is_available()

        if not self._service_available:
            logger.warning("SD service not available, skipping generation")
            return []

        # Determine dimensions based on orientation
        width, height = self._get_dimensions(orientation)

        client = await self._get_client()
        assets: list[VisualAsset] = []

        for i in range(count):
            try:
                response = await client.post(
                    f"{self._config.service_url}/generate",
                    json={
                        "prompt": prompt,
                        "negative_prompt": negative_prompt or self._config.negative_prompt,
                        "width": width,
                        "height": height,
                        "num_inference_steps": self._config.num_inference_steps,
                        "guidance_scale": self._config.guidance_scale,
                        "seed": seed,
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Store base64 data in metadata for later download
                assets.append(
                    VisualAsset(
                        type=VisualSourceType.AI_IMAGE,
                        url=None,  # No URL, data is in metadata
                        width=data.get("width", width),
                        height=data.get("height", height),
                        source="stable_diffusion",
                        source_id=f"sd_{data.get('seed', i)}",
                        license="Local Generation",
                        keywords=prompt.split()[:5],
                        metadata={
                            "prompt": prompt,
                            "negative_prompt": negative_prompt or self._config.negative_prompt,
                            "seed": data.get("seed"),
                            "image_base64": data.get("image"),
                            "num_inference_steps": self._config.num_inference_steps,
                            "guidance_scale": self._config.guidance_scale,
                        },
                    )
                )

                logger.info(f"Generated SD image {i + 1}/{count} (seed={data.get('seed')})")

            except httpx.HTTPStatusError as e:
                logger.error(
                    f"SD API error: {e.response.status_code} - " f"{e.response.text[:500]}"
                )
                continue
            except httpx.HTTPError as e:
                logger.error(f"SD request failed: {e}")
                # Mark service as potentially unavailable
                self._service_available = None
                continue
            except Exception as e:
                logger.error(f"SD generation failed: {e}", exc_info=True)
                continue

        logger.info(f"Generated {len(assets)} SD images for prompt: {prompt[:50]}...")
        return assets

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Save generated image to local storage.

        For SD images, the base64 data is stored in metadata.
        This method decodes and saves it to disk.

        Args:
            asset: Asset with base64 image data in metadata
            output_dir: Directory to save the file

        Returns:
            Asset with updated path

        Raises:
            ValueError: If asset has no image data
            RuntimeError: If save fails
        """
        image_base64 = asset.metadata.get("image_base64") if asset.metadata else None

        if not image_base64:
            raise ValueError("Asset has no image data to save")

        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"sd_{asset.source_id}.png"
        output_path = output_dir / filename

        # Skip if already saved
        if output_path.exists():
            logger.debug(f"Image already saved: {output_path}")
            asset.path = output_path
            return asset

        try:
            # Decode base64 and save
            image_data = base64.b64decode(image_base64)

            with open(output_path, "wb") as f:
                f.write(image_data)

            logger.info(f"Saved SD image: {output_path}")
            asset.path = output_path

            # Clear base64 data from metadata to save memory
            if asset.metadata:
                asset.metadata.pop("image_base64", None)

            return asset

        except Exception as e:
            raise RuntimeError(f"Failed to save image: {e}") from e

    def _get_dimensions(
        self,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> tuple[int, int]:
        """Get generation dimensions based on orientation.

        Args:
            orientation: Desired orientation

        Returns:
            Tuple of (width, height)
        """
        if orientation == "portrait":
            return self._config.base_width, self._config.base_height
        elif orientation == "landscape":
            return self._config.base_height, self._config.base_width
        else:
            # Square - use base_width for both
            return self._config.base_width, self._config.base_width

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


__all__ = ["StableDiffusionGenerator"]
