"""Visual sourcing manager.

Orchestrates visual asset sourcing from multiple sources with priority-based fallback.
"""

import logging
from pathlib import Path
from typing import Literal

from app.config.video import VisualConfig
from app.services.generator.visual.ai_image import AIImageGenerator
from app.services.generator.visual.base import VisualAsset
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.pexels import PexelsClient

logger = logging.getLogger(__name__)


class VisualSourcingManager:
    """Manage visual asset sourcing with priority-based fallback.

    Orchestrates sourcing from:
    1. Stock videos (Pexels)
    2. Stock images (Pexels)
    3. AI-generated images (DALL-E)
    4. Fallback backgrounds (solid/gradient)

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
        ai_generator: AIImageGenerator | None = None,
        fallback_generator: FallbackGenerator | None = None,
    ) -> None:
        """Initialize VisualSourcingManager.

        Args:
            config: Visual configuration
            pexels_client: Optional Pexels client instance
            ai_generator: Optional AI image generator instance
            fallback_generator: Optional fallback generator instance
        """
        self.config = config or VisualConfig()
        self._pexels = pexels_client or PexelsClient()
        self._ai_generator = ai_generator or AIImageGenerator()
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

        if source_type == "stock_video":
            return await self._pexels.search_videos(
                query=query,
                max_results=max_results,
                orientation=orientation,
                min_duration=3.0,
            )

        elif source_type == "stock_image":
            return await self._pexels.search_images(
                query=query,
                max_results=max_results,
                orientation=orientation,
            )

        elif source_type == "ai_image":
            # Generate 1-2 AI images
            return await self._ai_generator.generate(
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
        elif asset.source == "dalle":
            return await self._ai_generator.download(asset, output_dir)
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

    async def close(self) -> None:
        """Close all clients."""
        await self._pexels.close()
        await self._ai_generator.close()


__all__ = ["VisualSourcingManager"]
