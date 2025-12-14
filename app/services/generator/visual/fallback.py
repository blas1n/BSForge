"""Fallback visual generators.

Generates solid color and gradient backgrounds when stock/AI sources fail.
Uses PIL for image generation.
"""

import logging
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)

logger = logging.getLogger(__name__)


class FallbackGenerator(BaseVisualSource):
    """Generate fallback backgrounds (solid colors and gradients).

    Used as last resort when stock videos/images and AI generation fail.

    Example:
        >>> generator = FallbackGenerator()
        >>> solid = generator.create_solid("#1a1a2e", 1080, 1920)
        >>> gradient = generator.create_gradient(["#1a1a2e", "#16213e"], 1080, 1920)
    """

    def __init__(
        self,
        default_color: str = "#1a1a2e",
        default_gradient: list[str] | None = None,
    ) -> None:
        """Initialize FallbackGenerator.

        Args:
            default_color: Default solid color (hex)
            default_gradient: Default gradient colors (list of hex)
        """
        self._default_color = default_color
        self._default_gradient = default_gradient or ["#1a1a2e", "#16213e"]

    async def search(
        self,
        query: str,
        max_results: int = 1,
        orientation: Literal["portrait", "landscape", "square"] = "portrait",
        min_duration: float | None = None,
    ) -> list[VisualAsset]:
        """Generate fallback assets based on query.

        Note: Query is ignored; generates default backgrounds.

        Args:
            query: Ignored
            max_results: Number of assets to generate
            orientation: Image orientation
            min_duration: Ignored

        Returns:
            List of fallback assets (not yet saved to disk)
        """
        width, height = self._get_dimensions(orientation)

        assets: list[VisualAsset] = []

        # Generate solid color first
        if max_results >= 1:
            assets.append(
                VisualAsset(
                    type=VisualSourceType.SOLID_COLOR,
                    color=self._default_color,
                    width=width,
                    height=height,
                    source="fallback",
                    source_id=f"solid_{uuid4().hex[:8]}",
                )
            )

        # Then gradient
        if max_results >= 2:
            assets.append(
                VisualAsset(
                    type=VisualSourceType.GRADIENT,
                    gradient_colors=self._default_gradient,
                    width=width,
                    height=height,
                    source="fallback",
                    source_id=f"gradient_{uuid4().hex[:8]}",
                )
            )

        return assets

    async def download(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Generate and save fallback image.

        Args:
            asset: Asset descriptor
            output_dir: Directory to save the file

        Returns:
            Asset with updated path
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if asset.type == VisualSourceType.SOLID_COLOR:
            return self._create_solid_image(asset, output_dir)
        elif asset.type == VisualSourceType.GRADIENT:
            return self._create_gradient_image(asset, output_dir)
        else:
            raise ValueError(f"Unsupported fallback type: {asset.type}")

    def create_solid(
        self,
        color: str,
        width: int,
        height: int,
        output_dir: Path,
    ) -> VisualAsset:
        """Create a solid color image.

        Args:
            color: Hex color
            width: Image width
            height: Image height
            output_dir: Output directory

        Returns:
            Created visual asset
        """
        asset = VisualAsset(
            type=VisualSourceType.SOLID_COLOR,
            color=color,
            width=width,
            height=height,
            source="fallback",
            source_id=f"solid_{uuid4().hex[:8]}",
        )
        return self._create_solid_image(asset, output_dir)

    def create_gradient(
        self,
        colors: list[str],
        width: int,
        height: int,
        output_dir: Path,
        direction: Literal["vertical", "horizontal"] = "vertical",
    ) -> VisualAsset:
        """Create a gradient image.

        Args:
            colors: List of hex colors
            width: Image width
            height: Image height
            output_dir: Output directory
            direction: Gradient direction

        Returns:
            Created visual asset
        """
        asset = VisualAsset(
            type=VisualSourceType.GRADIENT,
            gradient_colors=colors,
            width=width,
            height=height,
            source="fallback",
            source_id=f"gradient_{uuid4().hex[:8]}",
            metadata={"direction": direction},
        )
        return self._create_gradient_image(asset, output_dir)

    def _create_solid_image(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Create solid color image file.

        Args:
            asset: Asset descriptor
            output_dir: Output directory

        Returns:
            Asset with path
        """
        from PIL import Image

        color = asset.color or self._default_color
        width = asset.width or 1080
        height = asset.height or 1920

        # Create image
        rgb = self._hex_to_rgb(color)
        image = Image.new("RGB", (width, height), rgb)

        # Save
        filename = f"{asset.source_id}.png"
        output_path = output_dir / filename
        image.save(output_path, "PNG")

        logger.info(f"Created solid color image: {output_path}")
        asset.path = output_path
        return asset

    def _create_gradient_image(
        self,
        asset: VisualAsset,
        output_dir: Path,
    ) -> VisualAsset:
        """Create gradient image file.

        Args:
            asset: Asset descriptor
            output_dir: Output directory

        Returns:
            Asset with path
        """
        from PIL import Image

        colors = asset.gradient_colors or self._default_gradient
        width = asset.width or 1080
        height = asset.height or 1920
        direction = asset.metadata.get("direction", "vertical")

        # Parse colors
        rgb_colors = [self._hex_to_rgb(c) for c in colors]

        # Create gradient
        image = Image.new("RGB", (width, height))
        pixels = image.load()
        if pixels is None:
            raise RuntimeError("Failed to load image pixels")

        if direction == "vertical":
            for y in range(height):
                # Calculate interpolation factor
                t = y / (height - 1) if height > 1 else 0
                color = self._interpolate_colors(rgb_colors, t)
                for x in range(width):
                    pixels[x, y] = color
        else:
            for x in range(width):
                t = x / (width - 1) if width > 1 else 0
                color = self._interpolate_colors(rgb_colors, t)
                for y in range(height):
                    pixels[x, y] = color

        # Save
        filename = f"{asset.source_id}.png"
        output_path = output_dir / filename
        image.save(output_path, "PNG")

        logger.info(f"Created gradient image: {output_path}")
        asset.path = output_path
        return asset

    def _hex_to_rgb(self, hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple.

        Args:
            hex_color: Hex color (e.g., "#FFFFFF")

        Returns:
            RGB tuple
        """
        hex_color = hex_color.lstrip("#")
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )

    def _interpolate_colors(
        self,
        colors: list[tuple[int, int, int]],
        t: float,
    ) -> tuple[int, int, int]:
        """Interpolate between multiple colors.

        Args:
            colors: List of RGB tuples
            t: Interpolation factor (0-1)

        Returns:
            Interpolated RGB tuple
        """
        if len(colors) == 1:
            return colors[0]

        # Find segment
        segment_count = len(colors) - 1
        segment_t = t * segment_count
        segment_idx = min(int(segment_t), segment_count - 1)
        local_t = segment_t - segment_idx

        # Interpolate between two colors
        c1 = colors[segment_idx]
        c2 = colors[segment_idx + 1]

        return (
            int(c1[0] + (c2[0] - c1[0]) * local_t),
            int(c1[1] + (c2[1] - c1[1]) * local_t),
            int(c1[2] + (c2[2] - c1[2]) * local_t),
        )

    def _get_dimensions(
        self,
        orientation: Literal["portrait", "landscape", "square"],
    ) -> tuple[int, int]:
        """Get dimensions for orientation.

        Args:
            orientation: Image orientation

        Returns:
            (width, height) tuple
        """
        if orientation == "portrait":
            return (1080, 1920)
        elif orientation == "landscape":
            return (1920, 1080)
        else:
            return (1080, 1080)


__all__ = ["FallbackGenerator"]
