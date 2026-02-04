"""Stable Diffusion HTTP client for image generation.

Communicates with the SD Docker service via HTTP API.
Provides graceful fallback when SD service is unavailable.
"""

import base64
import logging
import random
from pathlib import Path
from typing import Literal

from app.config.video import StableDiffusionConfig
from app.infrastructure.http_client import HTTPClient
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
        >>> http_client = HTTPClient()
        >>> generator = StableDiffusionGenerator(http_client)
        >>> if await generator.is_available():
        ...     images = await generator.generate("sunset over mountains")
        ...     downloaded = await generator.download(images[0], Path("/tmp"))
    """

    def __init__(
        self,
        http_client: HTTPClient,
        config: StableDiffusionConfig | None = None,
    ) -> None:
        """Initialize StableDiffusionGenerator.

        Args:
            http_client: Shared HTTP client for API requests
            config: SD service configuration
        """
        self._config = config or StableDiffusionConfig()
        self._client = http_client
        self._service_available: bool | None = None  # None = not checked yet

    async def is_available(self, force_check: bool = False) -> bool:
        """Check if SD service is available.

        Uses cached result unless force_check=True or service was marked unavailable.
        Call with force_check=True to re-verify after a failure.

        Args:
            force_check: Force a fresh health check

        Returns:
            True if service is healthy and responding
        """
        if not self._config.enabled:
            return False

        if self._service_available and not force_check:
            return True

        try:
            response = await self._client.get(
                f"{self._config.service_url}/health",
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                self._service_available = data.get("status") == "ok"
                if self._service_available:
                    logger.info(
                        f"SD service available: device={data.get('device')}, "
                        f"model_loaded={data.get('model_loaded')}"
                    )
                return self._service_available

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
        if not await self.is_available():
            logger.warning("SD service not available, skipping generation")
            return []

        # Determine dimensions based on orientation
        width, height = self._get_dimensions(orientation)

        assets: list[VisualAsset] = []

        for i in range(count):
            try:
                # Generate unique random seed for each image to ensure variety
                # If caller provides seed, use it only for first image and increment
                current_seed = seed + i if seed is not None else random.randint(0, 2**32 - 1)

                response = await self._client.post(
                    f"{self._config.service_url}/generate",
                    json={
                        "prompt": prompt,
                        "negative_prompt": negative_prompt or self._config.negative_prompt,
                        "width": width,
                        "height": height,
                        "num_inference_steps": self._config.num_inference_steps,
                        "guidance_scale": self._config.guidance_scale,
                        "seed": current_seed,
                    },
                    timeout=self._config.timeout,
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

            except Exception as e:
                logger.error(f"SD generation failed: {e}", exc_info=True)
                # Mark service as potentially unavailable
                self._service_available = False
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

    async def evaluate(self, file_path: Path, keyword: str) -> float | None:
        """Evaluate file-text similarity using CLIP.

        For images, calls /evaluate endpoint.
        For videos, calls /evaluate_video endpoint with multi-frame sampling.

        Args:
            file_path: Path to the image or video file
            keyword: Text/keyword to match against file

        Returns:
            Similarity score (0.0 to 1.0), or None if evaluation fails
        """
        if not await self.is_available():
            logger.warning("SD service not available, skipping CLIP evaluation")
            return None

        # Determine if file is video or image
        suffix = file_path.suffix.lower()
        is_video = suffix in (".mp4", ".webm", ".mov", ".avi", ".mkv")

        try:
            # Read and encode file
            with open(file_path, "rb") as f:
                file_base64 = base64.b64encode(f.read()).decode("utf-8")

            if is_video:
                # Use video evaluation endpoint with multi-frame sampling
                response = await self._client.post(
                    f"{self._config.service_url}/evaluate_video",
                    json={
                        "video": file_base64,
                        "text": keyword,
                        "num_frames": 5,  # Sample 5 frames across video
                    },
                    timeout=60.0,  # Video processing takes longer
                )
            else:
                # Use image evaluation endpoint
                response = await self._client.post(
                    f"{self._config.service_url}/evaluate",
                    json={
                        "image": file_base64,
                        "text": keyword,
                    },
                    timeout=30.0,
                )

            response.raise_for_status()
            data = response.json()

            score: float = data.get("score", 0.0)
            if is_video:
                min_score = data.get("min_score", score)
                max_score = data.get("max_score", score)
                logger.info(
                    f"CLIP video evaluation for '{keyword}': "
                    f"avg={score:.4f}, min={min_score:.4f}, max={max_score:.4f}"
                )
            else:
                logger.info(f"CLIP evaluation for '{keyword}': {score:.4f}")

            return score

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None
        except Exception as e:
            logger.error(f"CLIP evaluation failed: {e}", exc_info=True)
            self._service_available = False
            return None

    async def transform(
        self,
        source_image: Path,
        prompt: str,
        output_dir: Path,
        strength: float | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> VisualAsset | None:
        """Transform image using img2img.

        Calls the SD service's /img2img endpoint to transform an image.

        Args:
            source_image: Path to the source image
            prompt: Transformation prompt
            output_dir: Directory to save the result
            strength: Transformation strength (0.1-0.9), uses config default if None
            negative_prompt: Negative prompt override
            seed: Random seed for reproducibility

        Returns:
            Transformed image asset, or None if transformation fails
        """
        if not await self.is_available():
            logger.warning("SD service not available, skipping img2img")
            return None

        try:
            # Read and encode source image
            with open(source_image, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            # Generate random seed if not provided to ensure variety
            current_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

            response = await self._client.post(
                f"{self._config.service_url}/img2img",
                json={
                    "image": image_base64,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt or self._config.negative_prompt,
                    "strength": strength or self._config.img2img_strength,
                    "num_inference_steps": self._config.num_inference_steps,
                    "guidance_scale": self._config.guidance_scale,
                    "seed": current_seed,
                },
                timeout=self._config.timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Save the transformed image
            result_seed = data.get("seed", 0)
            filename = f"sd_img2img_{result_seed}.png"
            output_path = output_dir / filename

            result_base64 = data.get("image")
            if result_base64:
                image_data = base64.b64decode(result_base64)
                with open(output_path, "wb") as f:
                    f.write(image_data)

            logger.info(f"Transformed image saved: {output_path}")

            return VisualAsset(
                type=VisualSourceType.AI_IMAGE,
                url=None,
                width=data.get("width", 512),
                height=data.get("height", 768),
                source="stable_diffusion",
                source_id=f"sd_img2img_{result_seed}",
                path=output_path,
                license="Local Generation",
                keywords=prompt.split()[:5],
                metadata={
                    "prompt": prompt,
                    "negative_prompt": negative_prompt or self._config.negative_prompt,
                    "seed": result_seed,
                    "strength": strength or self._config.img2img_strength,
                    "source_image": str(source_image),
                    "num_inference_steps": self._config.num_inference_steps,
                    "guidance_scale": self._config.guidance_scale,
                },
            )

        except FileNotFoundError:
            logger.error(f"Source image not found: {source_image}")
            return None
        except Exception as e:
            logger.error(f"img2img transformation failed: {e}", exc_info=True)
            self._service_available = False
            return None

    async def upscale(
        self,
        source_image: Path,
        output_dir: Path,
        scale: int = 2,
    ) -> Path | None:
        """Upscale image using SD img2img with low strength.

        Uses Stable Diffusion's img2img pipeline with very low strength
        to enhance resolution while preserving the original content.

        Args:
            source_image: Path to source image
            output_dir: Output directory for upscaled image
            scale: Upscale factor (2, 3, or 4)

        Returns:
            Path to upscaled image, or None if upscaling fails
        """
        if not await self.is_available():
            logger.warning("SD service not available for upscaling")
            return None

        try:
            # Read and encode source image
            with open(source_image, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")

            logger.info(f"Upscaling image {source_image} with scale={scale}x")

            response = await self._client.post(
                f"{self._config.service_url}/upscale",
                json={
                    "image": image_base64,
                    "scale": scale,
                },
                timeout=120.0,  # Upscaling can take time
            )
            response.raise_for_status()
            data = response.json()

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            # Save the upscaled image
            filename = f"upscaled_{source_image.stem}.png"
            output_path = output_dir / filename

            result_base64 = data.get("image")
            if result_base64:
                image_data = base64.b64decode(result_base64)
                with open(output_path, "wb") as f:
                    f.write(image_data)

            original_size = f"{data.get('original_width')}x{data.get('original_height')}"
            new_size = f"{data.get('width')}x{data.get('height')}"
            logger.info(f"Upscaled {original_size} -> {new_size}: {output_path}")

            return output_path

        except FileNotFoundError:
            logger.error(f"Source image not found: {source_image}")
            return None
        except Exception as e:
            logger.error(f"Upscaling failed: {e}", exc_info=True)
            return None


__all__ = ["StableDiffusionGenerator"]
