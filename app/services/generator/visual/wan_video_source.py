"""Wan 2.2 HTTP client for text-to-video generation.

Communicates with the Wan Docker service via HTTP API.
Provides graceful fallback when the Wan service is unavailable.
"""

import base64
import random
from pathlib import Path
from typing import Literal

from app.config.video import WanConfig
from app.core.logging import get_logger
from app.infrastructure.http_client import HTTPClient
from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

logger = get_logger(__name__)


class WanVideoSource(BaseVisualSource):
    """Wan 2.2 T2V HTTP client.

    Communicates with the Wan service running in a separate Docker container.
    Generates short video clips from text prompts as background visuals.

    Example:
        >>> http_client = HTTPClient()
        >>> source = WanVideoSource(http_client)
        >>> if await source.is_available():
        ...     videos = await source.generate("dramatic sunset over city")
        ...     downloaded = await source.download(videos[0], Path("/tmp"))
    """

    def __init__(
        self,
        http_client: HTTPClient,
        config: WanConfig | None = None,
    ) -> None:
        """Initialize WanVideoSource.

        Args:
            http_client: Shared HTTP client for API requests
            config: Wan service configuration
        """
        self._config = config or WanConfig()
        self._client = http_client
        self._service_available: bool | None = None

    @property
    def default_duration(self) -> float:
        """Default clip duration in seconds."""
        return self._config.default_duration_seconds

    async def is_available(self, force_check: bool = False) -> bool:
        """Check if Wan service is available.

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
                        f"Wan service available: device={data.get('device')}, "
                        f"pipeline_loaded={data.get('pipeline_loaded')}, "
                        f"model={data.get('model_id')}"
                    )
                return self._service_available

        except Exception as e:
            logger.warning(f"Wan service check failed: {e}")

        self._service_available = False
        return False

    async def search(
        self,
        query: str,
        max_results: int = 1,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Generate videos based on query (implements BaseVisualSource).

        Args:
            query: Video description prompt
            max_results: Number of videos to generate
            orientation: Video orientation
            min_duration: Minimum duration (used to set generation duration)

        Returns:
            List of generated video assets
        """
        duration = max(min_duration or self._config.default_duration_seconds, 3.0)
        return await self.generate(
            prompt=query,
            count=max_results,
            orientation=orientation,
            duration_seconds=duration,
        )

    async def generate(
        self,
        prompt: str,
        count: int = 1,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        duration_seconds: float | None = None,
        seed: int | None = None,
    ) -> list[VisualAsset]:
        """Generate video clips using Wan 2.2.

        Args:
            prompt: Video description
            count: Number of videos to generate
            orientation: Video orientation
            duration_seconds: Duration per video
            seed: Random seed for reproducibility

        Returns:
            List of generated video assets (with base64 data in metadata)
        """
        if not await self.is_available():
            logger.warning("Wan service not available, skipping generation")
            return []

        width, height = self._get_dimensions(orientation)
        duration = duration_seconds or self._config.default_duration_seconds

        assets: list[VisualAsset] = []

        for i in range(count):
            try:
                current_seed = seed + i if seed is not None else random.randint(0, 2**32 - 1)

                response = await self._client.post(
                    f"{self._config.service_url}/generate",
                    json={
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "duration_seconds": duration,
                        "fps": self._config.default_fps,
                        "guidance_scale": 5.0,
                        "seed": current_seed,
                    },
                    timeout=self._config.timeout,
                )
                response.raise_for_status()
                data = response.json()

                assets.append(
                    VisualAsset(
                        type=VisualSourceType.AI_VIDEO,
                        url=None,
                        width=data.get("width", width),
                        height=data.get("height", height),
                        duration=data.get("duration_seconds", duration),
                        source="wan_video",
                        source_id=f"wan_{data.get('seed', i)}",
                        license="Local Generation",
                        keywords=prompt.split()[:5],
                        metadata={
                            "prompt": prompt,
                            "seed": data.get("seed"),
                            "fps": data.get("fps", self._config.default_fps),
                            "num_frames": data.get("num_frames"),
                            "video_base64": data.get("video"),
                        },
                    )
                )

                logger.info(
                    f"Generated Wan video {i + 1}/{count} "
                    f"({data.get('duration_seconds', duration):.1f}s, seed={data.get('seed')})"
                )

            except Exception as e:
                logger.error(f"Wan generation failed: {e}", exc_info=True)
                self._service_available = False
                continue

        logger.info(f"Generated {len(assets)} Wan videos for prompt: {prompt[:50]}...")
        return assets

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Save generated video to local storage.

        For Wan videos, base64 data is stored in metadata.
        This method decodes and saves it to disk.

        Args:
            asset: Asset with base64 video data in metadata
            output_dir: Directory to save the file

        Returns:
            Asset with updated path

        Raises:
            ValueError: If asset has no video data
            RuntimeError: If save fails
        """
        video_base64 = asset.metadata.get("video_base64") if asset.metadata else None

        if not video_base64:
            raise ValueError("Asset has no video data to save")

        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"wan_{asset.source_id}.mp4"
        output_path = output_dir / filename

        if output_path.exists():
            logger.debug(f"Video already saved: {output_path}")
            asset.path = output_path
            return asset

        try:
            video_data = base64.b64decode(video_base64)

            with open(output_path, "wb") as f:
                f.write(video_data)

            logger.info(f"Saved Wan video: {output_path}")
            asset.path = output_path

            # Clear base64 from metadata to free memory
            if asset.metadata:
                asset.metadata.pop("video_base64", None)

            return asset

        except Exception as e:
            raise RuntimeError(f"Failed to save video: {e}") from e

    async def evaluate(self, file_path: Path, keyword: str) -> float | None:
        """Evaluate video-text similarity using CLIP via Wan service.

        Args:
            file_path: Path to the video file
            keyword: Text/keyword to match against video

        Returns:
            Similarity score (0.0 to 1.0), or None if evaluation fails
        """
        if not await self.is_available():
            logger.warning("Wan service not available, skipping CLIP evaluation")
            return None

        try:
            with open(file_path, "rb") as f:
                file_base64 = base64.b64encode(f.read()).decode("utf-8")

            response = await self._client.post(
                f"{self._config.service_url}/evaluate_video",
                json={
                    "video": file_base64,
                    "text": keyword,
                    "num_frames": 5,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

            score: float = data.get("score", 0.0)
            logger.info(f"CLIP video eval '{keyword}': {score:.4f}")
            return score

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None
        except Exception as e:
            logger.error(f"CLIP evaluation failed: {e}", exc_info=True)
            self._service_available = False
            return None

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
            # Square - use smaller dimension for both
            side = min(self._config.base_width, self._config.base_height)
            return side, side


__all__ = ["WanVideoSource"]
