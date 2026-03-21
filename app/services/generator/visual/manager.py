"""Visual sourcing manager.

Orchestrates visual asset sourcing from Pexels (stock) and Wan (AI generation).

Source priority:
1. Pexels videos/images (stock)
2. Wan 2.2 AI video generation
3. Solid color fallback (generated locally)
"""

import asyncio
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx

from app.config.video import VisualConfig
from app.core.logging import get_logger
from app.infrastructure.http_client import HTTPClient
from app.services.generator.visual.base import VisualAsset
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.wan_video_source import WanVideoSource

if TYPE_CHECKING:
    from app.models.scene import Scene
    from app.services.generator.tts.base import SceneTTSResult

logger = get_logger(__name__)


@dataclass
class SceneVisualResult:
    """Visual sourcing result for a single scene.

    Attributes:
        scene_index: Index of the scene
        scene_type: Type of the scene (hook, content, commentary, etc.)
        asset: Visual asset for this scene
        duration: Duration this visual should be displayed
        start_offset: Global start time in final video
    """

    scene_index: int
    scene_type: str
    asset: VisualAsset
    duration: float
    start_offset: float


class VisualSourcingManager:
    """Manage visual asset sourcing with priority-based fallback.

    Sources:
    1. Pexels (stock videos/images)
    2. Wan 2.2 (AI-generated video)
    3. Solid color fallback
    """

    def __init__(
        self,
        http_client: HTTPClient,
        config: VisualConfig,
        pexels_client: PexelsClient,
        wan_video_source: WanVideoSource,
    ) -> None:
        """Initialize VisualSourcingManager.

        Args:
            http_client: Shared HTTP client for API requests
            config: Visual configuration
            pexels_client: Pexels client instance
            wan_video_source: Wan 2.2 video generation source instance
        """
        self.config = config
        self._http_client = http_client
        self._pexels = pexels_client
        self._wan_video = wan_video_source

    async def source_visuals_for_scenes(
        self,
        scenes: list["Scene"],
        scene_results: list["SceneTTSResult"],
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
    ) -> list[SceneVisualResult]:
        """Source visual assets for each scene individually.

        Args:
            scenes: List of Scene objects with keywords and strategies
            scene_results: List of SceneTTSResult with timing info
            output_dir: Directory to download assets
            orientation: Visual orientation

        Returns:
            List of SceneVisualResult, one per scene
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[SceneVisualResult] = []

        logger.info("sourcing_visuals", scene_count=len(scenes))

        last_asset: VisualAsset | None = None
        used_source_ids: set[tuple[str | None, str | None]] = set()
        reuse_types = self.config.reuse_previous_visual_types

        if len(scenes) != len(scene_results):
            logger.warning(
                "scene_tts_count_mismatch",
                scenes=len(scenes),
                tts_results=len(scene_results),
            )

        paired_count = min(len(scenes), len(scene_results))

        paired_scenes = zip(scenes[:paired_count], scene_results[:paired_count], strict=True)
        for i, (scene, tts_result) in enumerate(paired_scenes):
            keyword = scene.visual_keyword or scene.text[:50]
            duration = tts_result.duration_seconds
            start_offset = tts_result.start_offset

            # Reuse previous image for configured scene types (e.g., CTA)
            if scene.scene_type.value in reuse_types and last_asset is not None:
                reused_asset = replace(last_asset, duration=duration)
                results.append(
                    SceneVisualResult(
                        scene_index=i,
                        scene_type=scene.scene_type.value,
                        asset=reused_asset,
                        duration=duration,
                        start_offset=start_offset,
                    )
                )
                continue

            scene_dir = output_dir / f"scene_{i:03d}"
            try:
                async with asyncio.timeout(30):
                    asset = await self._source_for_scene(
                        keyword=keyword,
                        duration=duration,
                        output_dir=scene_dir,
                        orientation=orientation,
                        exclude_source_ids=used_source_ids,
                    )
                asset.duration = duration
                last_asset = asset

                # Track by (source, source_id) or (source, url) for deduplication
                asset_key = (asset.source, asset.source_id or asset.url)
                used_source_ids.add(asset_key)

                results.append(
                    SceneVisualResult(
                        scene_index=i,
                        scene_type=scene.scene_type.value,
                        asset=asset,
                        duration=duration,
                        start_offset=start_offset,
                    )
                )

            except (httpx.HTTPError, RuntimeError, ValueError, OSError, TimeoutError) as e:
                logger.warning(
                    "scene_visual_failed",
                    scene=i,
                    error_type=type(e).__name__,
                    error=str(e),
                )
                # Clean up partial downloads from failed attempt
                shutil.rmtree(scene_dir, ignore_errors=True)
                fallback_asset = await self._create_fallback(
                    output_dir=output_dir / f"scene_{i:03d}",
                    duration=duration,
                    orientation=orientation,
                )
                last_asset = fallback_asset
                results.append(
                    SceneVisualResult(
                        scene_index=i,
                        scene_type=scene.scene_type.value,
                        asset=fallback_asset,
                        duration=duration,
                        start_offset=start_offset,
                    )
                )

        # Generate fallback visuals for remaining scenes without TTS results
        if len(scenes) > paired_count:
            last_end = (
                (scene_results[-1].start_offset + scene_results[-1].duration_seconds)
                if scene_results
                else 0.0
            )
            default_duration = 3.0
            for i in range(paired_count, len(scenes)):
                scene = scenes[i]
                logger.warning("scene_missing_tts_result", scene=i)
                fallback_asset = await self._create_fallback(
                    output_dir=output_dir / f"scene_{i:03d}",
                    duration=default_duration,
                    orientation=orientation,
                )
                results.append(
                    SceneVisualResult(
                        scene_index=i,
                        scene_type=scene.scene_type.value,
                        asset=fallback_asset,
                        duration=default_duration,
                        start_offset=last_end,
                    )
                )
                last_end += default_duration

        logger.info("sourced_visuals", count=len(results))
        return results

    async def _source_for_scene(
        self,
        keyword: str,
        duration: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
        exclude_source_ids: set[tuple[str | None, str | None]] | None = None,
    ) -> VisualAsset:
        """Source a single visual asset for a scene.

        Priority: Pexels stock → Wan AI → fallback.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        exclude_ids = exclude_source_ids or set()
        metadata_threshold = self.config.metadata_score_threshold

        # Try Pexels (image and video)
        for source_type in ["pexels_image", "pexels_video"]:
            try:
                if source_type == "pexels_video":
                    assets = await self._pexels.search_videos(
                        query=keyword,
                        max_results=5,
                        orientation=orientation,
                        min_duration=3.0,
                    )
                else:
                    assets = await self._pexels.search_images(
                        query=keyword,
                        max_results=5,
                        orientation=orientation,
                    )

                assets = sorted(assets, key=lambda a: a.metadata_score or 0.0, reverse=True)

                for asset in assets:
                    asset_key = (asset.source, asset.source_id or asset.url)
                    if asset_key in exclude_ids:
                        continue
                    if (
                        asset.metadata_score is not None
                        and asset.metadata_score < metadata_threshold
                    ):
                        continue

                    if not asset.is_downloaded:
                        asset = await self._pexels.download(asset, output_dir)
                    return asset

            except Exception as e:
                logger.warning(
                    "pexels_search_failed",
                    source_type=source_type,
                    keyword=keyword,
                    error=str(e),
                )

        # Try Wan AI video
        try:
            if await self._wan_video.is_available():
                prompt = keyword if keyword else "abstract digital background"
                wan_assets = await self._wan_video.generate(
                    prompt=prompt,
                    count=1,
                    orientation=orientation,
                    duration_seconds=self._wan_video.default_duration,
                )
                if wan_assets:
                    asset = wan_assets[0]
                    if not asset.is_downloaded:
                        asset = await self._wan_video.download(asset, output_dir)
                    return asset
        except Exception as e:
            logger.warning("wan_generation_failed", error=str(e))

        # Fallback
        return await self._create_fallback(output_dir, duration, orientation)

    async def _create_fallback(
        self,
        output_dir: Path,
        duration: float,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> VisualAsset:
        """Create a solid color fallback visual."""
        from app.services.generator.visual.base import VisualSourceType

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate a simple solid color image
        try:
            from PIL import Image

            if orientation == "portrait":
                size = (1080, 1920)
            elif orientation == "landscape":
                size = (1920, 1080)
            else:
                size = (1080, 1080)

            img = Image.new("RGB", size, color=(20, 20, 30))
            path = output_dir / "fallback.png"
            img.save(str(path))

            return VisualAsset(
                type=VisualSourceType.SOLID_COLOR,
                url="",
                path=path,
                duration=duration,
                width=size[0],
                height=size[1],
                source="fallback",
                source_id="fallback",
                license="generated",
            )
        except ImportError as err:
            raise RuntimeError("Pillow is required for fallback visual generation") from err

    async def __aenter__(self) -> "VisualSourcingManager":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close all clients."""
        for client in (self._pexels, self._wan_video):
            try:
                await client.close()
            except Exception:
                logger.warning(
                    "visual_client_close_error",
                    client=type(client).__name__,
                    exc_info=True,
                )


__all__ = ["VisualSourcingManager", "SceneVisualResult"]
