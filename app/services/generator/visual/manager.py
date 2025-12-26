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
from app.infrastructure.http_client import HTTPClient
from app.services.generator.visual.base import VisualAsset
from app.services.generator.visual.dall_e import DALLEGenerator
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.pixabay import PixabayClient
from app.services.generator.visual.stable_diffusion import StableDiffusionGenerator

if TYPE_CHECKING:
    from app.models.scene import Scene
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
        http_client: HTTPClient,
        config: VisualConfig | None = None,
        pexels_client: PexelsClient | None = None,
        pixabay_client: PixabayClient | None = None,
        dalle_generator: DALLEGenerator | None = None,
        sd_generator: StableDiffusionGenerator | None = None,
        fallback_generator: FallbackGenerator | None = None,
    ) -> None:
        """Initialize VisualSourcingManager.

        Args:
            http_client: Shared HTTP client for API requests
            config: Visual configuration
            pexels_client: Optional Pexels client instance
            pixabay_client: Optional Pixabay client instance
            dalle_generator: Optional DALL-E generator instance
            sd_generator: Optional Stable Diffusion generator instance
            fallback_generator: Optional fallback generator instance
        """
        self.config = config or VisualConfig()
        self._http_client = http_client
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
            self._sd_generator = StableDiffusionGenerator(
                http_client=self._http_client,
                config=self.config.stable_diffusion,
            )

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
                self._sd_generator = StableDiffusionGenerator(
                    http_client=self._http_client,
                    config=self.config.stable_diffusion,
                )
            return await self._sd_generator.download(asset, output_dir)
        elif asset.source == "fallback":
            return await self._fallback.download(asset, output_dir)
        else:
            raise ValueError(f"Unknown asset source: {asset.source}")

    def _build_ai_prompt(self, keywords: list[str]) -> str:
        """Build AI image prompt from keywords.

        visual_keyword already contains scene-specific style info,
        so we just add common quality suffix from config.

        Args:
            keywords: Keywords to incorporate (from visual_keyword)

        Returns:
            AI prompt string
        """
        if not keywords:
            return "abstract digital background, modern, professional"

        prompt = ", ".join(keywords)

        # Add quality suffix from SD config
        quality_suffix = self.config.stable_diffusion.ai_quality_suffix
        if quality_suffix:
            prompt += f", {quality_suffix}"

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
        and visual_strategy to determine the best source strategy. This enables
        scene-specific visual treatment (e.g., different visuals for
        COMMENTARY vs CONTENT scenes).

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

        logger.info(f"Sourcing visuals for {len(scenes)} scenes")

        # Track last asset for scene reuse (configurable scene types)
        last_asset: VisualAsset | None = None
        # Track used source IDs to avoid duplicates across scenes
        used_source_ids: set[str] = set()
        # Get reuse types from config (lowercase scene type names)
        reuse_types = self.config.reuse_previous_visual_types

        for i, (scene, tts_result) in enumerate(zip(scenes, scene_results, strict=False)):
            # Get scene-specific parameters
            keyword = scene.visual_keyword or scene.text[:50]
            duration = tts_result.duration_seconds
            start_offset = tts_result.start_offset

            logger.info(
                f"[Scene {i}] type={scene.scene_type.value}, "
                f"visual_keyword='{scene.visual_keyword}'"
            )

            # Reuse previous image for configured scene types (e.g., CTA - short)
            if scene.scene_type.value in reuse_types and last_asset is not None:
                logger.info(
                    f"  [{scene.scene_type.value.upper()}] Reusing previous image: "
                    f"{last_asset.source_id}"
                )
                # Create a copy with updated duration
                reused_asset = VisualAsset(
                    type=last_asset.type,
                    url=last_asset.url,
                    path=last_asset.path,
                    duration=duration,
                    width=last_asset.width,
                    height=last_asset.height,
                    source=last_asset.source,
                    source_id=last_asset.source_id,
                    license=last_asset.license,
                    keywords=last_asset.keywords,
                    metadata=last_asset.metadata,
                    metadata_score=last_asset.metadata_score,
                )
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

            try:
                asset = await self._source_for_scene(
                    keyword=keyword,
                    duration=duration,
                    output_dir=output_dir / f"scene_{i:03d}",
                    orientation=orientation,
                    exclude_source_ids=used_source_ids,
                )

                # Ensure asset has correct duration
                asset.duration = duration

                # Update last_asset for potential CTA reuse
                last_asset = asset

                # Track used source IDs to avoid duplicates
                if asset.source_id:
                    used_source_ids.add(asset.source_id)

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

                # Update last_asset even for fallback
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

        logger.info(f"Sourced {len(results)} scene visuals")
        return results

    async def _source_for_scene(
        self,
        keyword: str,
        duration: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
        exclude_source_ids: set[str] | None = None,
    ) -> VisualAsset:
        """Source a single visual asset for a scene.

        Uses stock search with quality check, falls back to AI generation.

        Args:
            keyword: Search keyword
            duration: Duration needed
            output_dir: Output directory
            orientation: Visual orientation
            exclude_source_ids: Set of source IDs to exclude (already used)

        Returns:
            Downloaded visual asset
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        exclude_ids = exclude_source_ids or set()

        return await self._source_stock_with_quality_check(
            keyword=keyword,
            duration=duration,
            output_dir=output_dir,
            orientation=orientation,
            exclude_source_ids=exclude_ids,
        )

    async def _source_stock_with_quality_check(
        self,
        keyword: str,
        duration: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
        exclude_source_ids: set[str] | None = None,
    ) -> VisualAsset:
        """Source from stock with hybrid quality evaluation.

        1st pass: Filter by metadata_score (fast, title/tags matching)
        2nd pass: Evaluate with CLIP (slower, visual similarity)
        3-tier CLIP decision:
          - score >= clip_threshold: use as-is
          - score >= clip_img2img_threshold: use img2img
          - score < clip_img2img_threshold: skip, try next or AI

        Args:
            keyword: Search keyword
            duration: Duration needed
            output_dir: Output directory
            orientation: Visual orientation
            exclude_source_ids: Set of source IDs to exclude (already used)

        Returns:
            Visual asset
        """
        # Get thresholds from config
        metadata_threshold = self.config.metadata_score_threshold
        clip_threshold = self.config.clip_score_threshold
        clip_img2img_threshold = self.config.clip_img2img_threshold
        exclude_ids = exclude_source_ids or set()

        # Try stock sources
        stock_sources = ["pexels_image", "pixabay_image", "pexels_video", "pixabay_video"]

        for source_type in stock_sources:
            try:
                assets = await self._source_from_type(
                    source_type=source_type,
                    keywords=[keyword],
                    duration_needed=duration,
                    output_dir=output_dir,
                    orientation=orientation,
                    image_duration=duration,
                )

                # Sort by metadata_score descending
                assets = sorted(
                    assets,
                    key=lambda a: a.metadata_score or 0.0,
                    reverse=True,
                )

                for asset in assets:
                    # Skip already used sources
                    if asset.source_id and asset.source_id in exclude_ids:
                        logger.info(f"  [SKIP] {asset.source}:{asset.source_id} already used")
                        continue

                    # 1st pass: metadata filter
                    meta_score = asset.metadata_score or 0.0
                    if meta_score < metadata_threshold:
                        logger.info(
                            f"  [SKIP] {asset.source}:{asset.source_id} "
                            f"metadata={meta_score:.2f} < threshold={metadata_threshold}"
                        )
                        continue

                    logger.info(
                        f"  [EVAL] {asset.source}:{asset.source_id} "
                        f"metadata={meta_score:.2f} (>= {metadata_threshold})"
                    )

                    # Download for CLIP evaluation
                    if not asset.is_downloaded:
                        try:
                            asset = await self._download_asset(asset, output_dir)
                        except Exception as e:
                            logger.warning(f"Failed to download {asset.source_id}: {e}")
                            continue

                    # 2nd pass: CLIP evaluation (if SD service available)
                    clip_score = await self._evaluate_with_clip(asset, keyword)

                    if clip_score is None:
                        # CLIP not available, use metadata score as fallback
                        logger.info(
                            f"  [SELECT] {asset.source}:{asset.source_id} "
                            f"(CLIP unavailable, using metadata score)"
                        )
                        return asset

                    if clip_score >= clip_threshold:
                        # Good match, use as-is
                        logger.info(
                            f"  [SELECT] {asset.source}:{asset.source_id} "
                            f"CLIP={clip_score:.3f} >= {clip_threshold} (use as-is)"
                        )
                        return asset

                    if clip_score >= clip_img2img_threshold:
                        # Medium match, try img2img
                        logger.info(
                            f"  [TRANSFORM] {asset.source}:{asset.source_id} "
                            f"CLIP={clip_score:.3f} in [{clip_img2img_threshold}, {clip_threshold})"
                        )
                        transformed = await self._transform_with_sd(
                            asset=asset,
                            keyword=keyword,
                            output_dir=output_dir,
                        )
                        if transformed:
                            logger.info(f"  [SELECT] transformed -> {transformed.source_id}")
                            return transformed
                        # If transform failed, still use original
                        logger.info(
                            f"  [SELECT] {asset.source}:{asset.source_id} "
                            f"(transform failed, using original)"
                        )
                        return asset

                    # Low score, try next asset
                    logger.info(
                        f"  [SKIP] {asset.source}:{asset.source_id} "
                        f"CLIP={clip_score:.3f} < {clip_img2img_threshold}"
                    )

            except Exception as e:
                logger.warning(f"Source {source_type} failed: {e}")
                continue

        # All stock sources failed or low quality, try AI generation
        logger.info(f"No quality stock found for '{keyword}', trying AI generation")
        return await self._source_ai_only(
            keywords=[keyword],
            duration=duration,
            output_dir=output_dir,
            orientation=orientation,
        )

    async def _source_stock_with_transform(
        self,
        keyword: str,
        duration: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
        exclude_source_ids: set[str] | None = None,
    ) -> VisualAsset:
        """Source from stock and always apply img2img transformation.

        This strategy is for style consistency - even if stock image matches,
        we transform it through SD to unify visual style.

        Args:
            keyword: Search keyword
            duration: Duration needed
            output_dir: Output directory
            orientation: Visual orientation
            exclude_source_ids: Set of source IDs to exclude (already used)

        Returns:
            Visual asset (transformed if possible)
        """
        metadata_threshold = self.config.metadata_score_threshold
        exclude_ids = exclude_source_ids or set()

        # Try stock sources (images only, videos can't be transformed)
        stock_sources = ["pexels_image", "pixabay_image"]

        best_asset: VisualAsset | None = None
        best_score: float = 0.0

        for source_type in stock_sources:
            try:
                assets = await self._source_from_type(
                    source_type=source_type,
                    keywords=[keyword],
                    duration_needed=duration,
                    output_dir=output_dir,
                    orientation=orientation,
                    image_duration=duration,
                )

                for asset in assets:
                    # Skip already used sources
                    if asset.source_id and asset.source_id in exclude_ids:
                        continue

                    score = asset.metadata_score or 0.0
                    if score >= metadata_threshold and score > best_score:
                        best_asset = asset
                        best_score = score

            except Exception as e:
                logger.warning(f"Source {source_type} failed: {e}")
                continue

        if best_asset and not best_asset.is_downloaded:
            # Download if needed
            try:
                best_asset = await self._download_asset(best_asset, output_dir)
            except Exception as e:
                logger.warning(f"Failed to download best asset: {e}")
                best_asset = None

        if best_asset:
            # Always try to transform
            transformed = await self._transform_with_sd(
                asset=best_asset,
                keyword=keyword,
                output_dir=output_dir,
            )
            if transformed:
                return transformed
            # Transform failed, use original
            return best_asset

        # No stock found, fall back to AI
        return await self._source_ai_only(
            keywords=[keyword],
            duration=duration,
            output_dir=output_dir,
            orientation=orientation,
        )

    async def _source_ai_only(
        self,
        keywords: list[str],
        duration: float,
        output_dir: Path,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> VisualAsset:
        """Source using AI generation only (SD or DALL-E).

        Args:
            keywords: Keywords for prompt generation
            duration: Duration needed
            output_dir: Output directory
            orientation: Visual orientation

        Returns:
            Visual asset
        """
        prompt = self._build_ai_prompt(keywords)

        # Try Stable Diffusion first (local, no API cost)
        try:
            assets = await self._generate_with_sd(
                prompt=prompt,
                count=1,
                orientation=orientation,
            )
            if assets and self._sd_generator is not None:
                asset = assets[0]
                if not asset.is_downloaded:
                    asset = await self._sd_generator.download(asset, output_dir)
                return asset
        except Exception as e:
            logger.warning(f"SD generation failed: {e}")

        # Try DALL-E as fallback
        try:
            assets = await self._dalle_generator.generate(
                prompt=prompt,
                count=1,
                orientation=orientation,
            )
            if assets:
                asset = assets[0]
                if not asset.is_downloaded:
                    asset = await self._dalle_generator.download(asset, output_dir)
                return asset
        except Exception as e:
            logger.warning(f"DALL-E generation failed: {e}")

        # All AI failed, use fallback
        return await self._create_fallback_for_scene(
            output_dir=output_dir,
            duration=duration,
            orientation=orientation,
        )

    async def _evaluate_with_clip(
        self,
        asset: VisualAsset,
        keyword: str,
    ) -> float | None:
        """Evaluate asset-keyword similarity using CLIP.

        Args:
            asset: Asset to evaluate (must be downloaded)
            keyword: Keyword to match

        Returns:
            CLIP score (0.0-1.0) or None if unavailable
        """
        if not asset.path or not asset.path.exists():
            return None

        # Lazy initialize SD generator
        if self._sd_generator is None:
            self._sd_generator = StableDiffusionGenerator(
                http_client=self._http_client,
                config=self.config.stable_diffusion,
            )

        return await self._sd_generator.evaluate(asset.path, keyword)

    async def _transform_with_sd(
        self,
        asset: VisualAsset,
        keyword: str,
        output_dir: Path,
    ) -> VisualAsset | None:
        """Transform asset using SD img2img.

        Args:
            asset: Asset to transform (must be downloaded)
            keyword: Prompt keyword
            output_dir: Output directory

        Returns:
            Transformed asset or None if failed
        """
        if not asset.path or not asset.path.exists():
            return None

        # img2img only works with images, skip video files
        if asset.is_video:
            logger.debug(f"Skipping img2img for video file: {asset.path}")
            return None

        # Lazy initialize SD generator
        if self._sd_generator is None:
            self._sd_generator = StableDiffusionGenerator(
                http_client=self._http_client,
                config=self.config.stable_diffusion,
            )

        prompt = self._build_ai_prompt([keyword])
        return await self._sd_generator.transform(
            source_image=asset.path,
            prompt=prompt,
            output_dir=output_dir,
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


__all__ = ["VisualSourcingManager", "SceneVisualResult"]
