"""Visual sourcing manager.

Orchestrates visual asset sourcing from multiple sources with priority-based fallback.
Supports scene-based visual sourcing for BSForge's scene architecture.

Source priority (configurable):
1. Pexels videos
2. Pixabay videos
3. Pexels images
4. Pixabay images
5. AI images (Stable Diffusion or DALL-E)
6. Fallback (solid color/gradient)
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from app.config.video import VisualConfig
from app.services.generator.visual.base import VisualAsset
from app.services.generator.visual.dall_e import DALLEGenerator
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.pixabay import PixabayClient
from app.services.generator.visual.stable_diffusion import StableDiffusionGenerator

if TYPE_CHECKING:
    from app.models.scene import Scene, VisualHintType
    from app.services.generator.tts.base import SceneTTSResult

logger = logging.getLogger(__name__)


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

    Orchestrates sourcing from:
    1. Stock videos (Pexels)
    2. Stock videos (Pixabay)
    3. Stock images (Pexels)
    4. Stock images (Pixabay)
    5. AI-generated images (Stable Diffusion or DALL-E)
    6. Fallback backgrounds (solid/gradient)

    Example:
        >>> manager = VisualSourcingManager()
        >>> assets = await manager.source_visuals(
        ...     keywords=["technology", "innovation"],
        ...     duration_needed=55.0,
        ...     output_dir=Path("/tmp/visuals"),
        ... )
    """

    def __init__(
        self,
        config: VisualConfig | None = None,
        pexels_client: PexelsClient | None = None,
        pixabay_client: PixabayClient | None = None,
        dalle_generator: DALLEGenerator | None = None,
        sd_generator: StableDiffusionGenerator | None = None,
        fallback_generator: FallbackGenerator | None = None,
    ) -> None:
        """Initialize VisualSourcingManager.

        Args:
            config: Visual configuration
            pexels_client: Optional Pexels client instance
            pixabay_client: Optional Pixabay client instance
            dalle_generator: Optional DALL-E generator instance
            sd_generator: Optional Stable Diffusion generator instance
            fallback_generator: Optional fallback generator instance
        """
        self.config = config or VisualConfig()
        self._pexels = pexels_client or PexelsClient()
        self._pixabay = pixabay_client or PixabayClient()
        self._dalle_generator = dalle_generator or DALLEGenerator()
        self._sd_generator = sd_generator  # Lazy initialized if needed
        self._fallback = fallback_generator or FallbackGenerator(
            default_color=self.config.fallback_color,
            default_gradient=self.config.fallback_gradient,
        )

    async def source_visuals(
        self,
        keywords: list[str],
        duration_needed: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
    ) -> list[VisualAsset]:
        """Source visual assets for video generation.

        Attempts to gather enough visuals to cover the required duration.
        Uses priority-based sourcing with fallback.

        Args:
            keywords: Search keywords
            duration_needed: Total duration needed in seconds
            output_dir: Directory to download assets
            orientation: Visual orientation

        Returns:
            List of visual assets (downloaded)
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        assets: list[VisualAsset] = []
        current_duration = 0.0

        # Default duration for images
        image_duration = 5.0

        logger.info(f"Sourcing visuals for {duration_needed}s, keywords: {keywords}")

        # Try each source type in priority order
        for source_type in self.config.source_priority:
            if current_duration >= duration_needed:
                break

            remaining = duration_needed - current_duration

            try:
                new_assets = await self._source_from_type(
                    source_type=source_type,
                    keywords=keywords,
                    duration_needed=remaining,
                    output_dir=output_dir,
                    orientation=orientation,
                    image_duration=image_duration,
                )

                for asset in new_assets:
                    if current_duration >= duration_needed:
                        break

                    # Download if not already downloaded
                    if not asset.is_downloaded:
                        try:
                            asset = await self._download_asset(asset, output_dir)
                        except Exception as e:
                            logger.warning(f"Failed to download {asset.source_id}: {e}")
                            continue

                    assets.append(asset)

                    # Update duration
                    if asset.is_video and asset.duration:
                        current_duration += asset.duration
                    else:
                        current_duration += image_duration

            except Exception as e:
                logger.warning(f"Source {source_type} failed: {e}")
                continue

        # Ensure we have at least fallback
        if not assets:
            logger.warning("No assets found, using fallback")
            fallback_assets = await self._fallback.search(
                query="",
                max_results=1,
                orientation=orientation,
            )
            if fallback_assets:
                asset = await self._fallback.download(fallback_assets[0], output_dir)
                asset.duration = duration_needed
                assets.append(asset)

        # Adjust last asset duration if needed
        if assets:
            total_duration = sum((a.duration or image_duration) for a in assets)
            if total_duration < duration_needed and assets[-1].is_image:
                # Extend last image duration
                assets[-1].duration = (assets[-1].duration or image_duration) + (
                    duration_needed - total_duration
                )

        logger.info(f"Sourced {len(assets)} visual assets")
        return assets

    async def _source_from_type(
        self,
        source_type: str,
        keywords: list[str],
        duration_needed: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
        image_duration: float,
    ) -> list[VisualAsset]:
        """Source assets from a specific type.

        Args:
            source_type: Source type string
            keywords: Search keywords
            duration_needed: Duration needed
            output_dir: Output directory
            orientation: Orientation
            image_duration: Default image duration

        Returns:
            List of visual assets
        """
        query = " ".join(keywords[:3])  # Use first 3 keywords
        max_results = max(1, int(duration_needed / image_duration) + 2)

        if source_type == "pexels_video":
            return await self._pexels.search_videos(
                query=query,
                max_results=max_results,
                orientation=orientation,
                min_duration=3.0,
            )

        elif source_type == "pixabay_video":
            return await self._pixabay.search_videos(
                query=query,
                max_results=max_results,
                orientation=orientation,
                min_duration=3.0,
            )

        elif source_type == "pexels_image":
            return await self._pexels.search_images(
                query=query,
                max_results=max_results,
                orientation=orientation,
            )

        elif source_type == "pixabay_image":
            return await self._pixabay.search_images(
                query=query,
                max_results=max_results,
                orientation=orientation,
            )

        elif source_type == "stable_diffusion":
            return await self._generate_with_sd(
                prompt=self._build_ai_prompt(keywords),
                count=min(2, max_results),
                orientation=orientation,
            )

        elif source_type == "dalle":
            return await self._dalle_generator.generate(
                prompt=self._build_ai_prompt(keywords),
                count=min(2, max_results),
                orientation=orientation,
            )

        elif source_type in ("solid_color", "gradient"):
            return await self._fallback.search(
                query="",
                max_results=1,
                orientation=orientation,
            )

        else:
            logger.warning(f"Unknown source type: {source_type}")
            return []

    async def _generate_with_sd(
        self,
        prompt: str,
        count: int,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> list[VisualAsset]:
        """Generate images with Stable Diffusion.

        Lazily initializes SD generator and checks availability.

        Args:
            prompt: Image prompt
            count: Number of images
            orientation: Image orientation

        Returns:
            List of generated assets, empty if SD unavailable
        """
        # Lazy initialize SD generator
        if self._sd_generator is None:
            self._sd_generator = StableDiffusionGenerator(config=self.config.stable_diffusion)

        # Check if SD service is available
        if not await self._sd_generator.is_available():
            return []

        return await self._sd_generator.generate(
            prompt=prompt,
            count=count,
            orientation=orientation,
        )

    async def _download_asset(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Download asset using appropriate client.

        Args:
            asset: Asset to download
            output_dir: Output directory

        Returns:
            Downloaded asset
        """
        if asset.source == "pexels":
            return await self._pexels.download(asset, output_dir)
        elif asset.source == "pixabay":
            return await self._pixabay.download(asset, output_dir)
        elif asset.source == "dalle":
            return await self._dalle_generator.download(asset, output_dir)
        elif asset.source == "stable_diffusion":
            if self._sd_generator is None:
                self._sd_generator = StableDiffusionGenerator(config=self.config.stable_diffusion)
            return await self._sd_generator.download(asset, output_dir)
        elif asset.source == "fallback":
            return await self._fallback.download(asset, output_dir)
        else:
            raise ValueError(f"Unknown asset source: {asset.source}")

    def _build_ai_prompt(self, keywords: list[str]) -> str:
        """Build AI image prompt from keywords.

        Args:
            keywords: Keywords to incorporate

        Returns:
            AI prompt string
        """
        if not keywords:
            return "abstract digital background, modern, professional"

        # Build descriptive prompt
        main_topic = keywords[0]
        modifiers = keywords[1:3] if len(keywords) > 1 else []

        prompt = f"{main_topic}"
        if modifiers:
            prompt += f", {', '.join(modifiers)}"

        prompt += ", modern digital art style, abstract background"

        return prompt

    async def source_visuals_for_scenes(
        self,
        scenes: list["Scene"],
        scene_results: list["SceneTTSResult"],
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
    ) -> list[SceneVisualResult]:
        """Source visual assets for each scene individually.

        This method sources one visual per scene, using the scene's keyword
        and visual_hint to determine the best source strategy. This enables
        scene-specific visual treatment (e.g., different visuals for
        COMMENTARY vs CONTENT scenes).

        Args:
            scenes: List of Scene objects with keywords and hints
            scene_results: List of SceneTTSResult with timing info
            output_dir: Directory to download assets
            orientation: Visual orientation

        Returns:
            List of SceneVisualResult, one per scene
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[SceneVisualResult] = []

        logger.info(f"Sourcing visuals for {len(scenes)} scenes")

        for i, (scene, tts_result) in enumerate(zip(scenes, scene_results, strict=False)):
            # Get scene-specific parameters
            keyword = scene.keyword or scene.text[:50]  # Fallback to text
            hint = scene.visual_hint
            duration = tts_result.duration_seconds
            start_offset = tts_result.start_offset

            logger.debug(
                f"Scene {i}: type={scene.scene_type.value}, "
                f"hint={hint.value}, keyword={keyword[:30]}"
            )

            try:
                asset = await self._source_for_scene(
                    keyword=keyword,
                    visual_hint=hint,
                    duration=duration,
                    output_dir=output_dir / f"scene_{i:03d}",
                    orientation=orientation,
                )

                # Ensure asset has correct duration
                asset.duration = duration

                results.append(
                    SceneVisualResult(
                        scene_index=i,
                        scene_type=scene.scene_type.value,
                        asset=asset,
                        duration=duration,
                        start_offset=start_offset,
                    )
                )

            except Exception as e:
                logger.warning(f"Failed to source visual for scene {i}: {e}")

                # Use fallback
                fallback_asset = await self._create_fallback_for_scene(
                    output_dir=output_dir / f"scene_{i:03d}",
                    duration=duration,
                    orientation=orientation,
                )

                results.append(
                    SceneVisualResult(
                        scene_index=i,
                        scene_type=scene.scene_type.value,
                        asset=fallback_asset,
                        duration=duration,
                        start_offset=start_offset,
                    )
                )

        logger.info(f"Sourced {len(results)} scene visuals")
        return results

    async def _source_for_scene(
        self,
        keyword: str,
        visual_hint: "VisualHintType",
        duration: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> VisualAsset:
        """Source a single visual asset for a scene.

        Uses the visual_hint to determine which source to try first.

        Args:
            keyword: Search keyword
            visual_hint: Hint for preferred source type
            duration: Duration needed
            output_dir: Output directory
            orientation: Visual orientation

        Returns:
            Downloaded visual asset
        """
        from app.models.scene import VisualHintType

        output_dir.mkdir(parents=True, exist_ok=True)

        # Map visual hint to source type
        hint_to_source = {
            VisualHintType.STOCK_VIDEO: "pexels_video",
            VisualHintType.STOCK_IMAGE: "pexels_image",
            VisualHintType.AI_GENERATED: "stable_diffusion",
            VisualHintType.TEXT_OVERLAY: "solid_color",
            VisualHintType.SOLID_COLOR: "solid_color",
        }

        preferred_source = hint_to_source.get(visual_hint, "pexels_image")

        # Build source priority based on hint
        # Preferred source first, then fallback through others
        source_order = [preferred_source]
        for src in ["pexels_image", "pexels_video", "stable_diffusion", "dalle", "solid_color"]:
            if src not in source_order:
                source_order.append(src)

        # Try each source in order
        for source_type in source_order:
            try:
                assets = await self._source_from_type(
                    source_type=source_type,
                    keywords=[keyword],
                    duration_needed=duration,
                    output_dir=output_dir,
                    orientation=orientation,
                    image_duration=duration,
                )

                if assets:
                    asset = assets[0]

                    # Download if needed
                    if not asset.is_downloaded:
                        asset = await self._download_asset(asset, output_dir)

                    return asset

            except Exception as e:
                logger.debug(f"Source {source_type} failed for keyword '{keyword}': {e}")
                continue

        # Final fallback
        return await self._create_fallback_for_scene(
            output_dir=output_dir,
            duration=duration,
            orientation=orientation,
        )

    async def _create_fallback_for_scene(
        self,
        output_dir: Path,
        duration: float,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> VisualAsset:
        """Create a fallback visual for a scene.

        Args:
            output_dir: Output directory
            duration: Duration for the visual
            orientation: Visual orientation

        Returns:
            Fallback visual asset
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        fallback_assets = await self._fallback.search(
            query="",
            max_results=1,
            orientation=orientation,
        )

        if fallback_assets:
            asset = await self._fallback.download(fallback_assets[0], output_dir)
            asset.duration = duration
            return asset

        # Absolute fallback - should never reach here
        raise RuntimeError("Failed to create fallback visual")

    async def close(self) -> None:
        """Close all clients."""
        await self._pexels.close()
        await self._pixabay.close()
        await self._dalle_generator.close()
        if self._sd_generator:
            await self._sd_generator.close()


__all__ = ["VisualSourcingManager", "SceneVisualResult"]
