"""Thumbnail generation service.

Generates YouTube thumbnail images using PIL.
Uses FFmpegWrapper SDK for video frame extraction.
"""

import tempfile
import textwrap
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.config.video import ThumbnailConfig
from app.core.logging import get_logger
from app.infrastructure.fonts import find_font_by_name
from app.services.generator.ffmpeg import FFmpegWrapper, get_ffmpeg_wrapper
from app.services.generator.visual.base import VisualAsset

logger = get_logger(__name__)


class ThumbnailGenerator:
    """Generate YouTube thumbnails.

    Features:
    - Background from visual asset or solid color
    - Semi-transparent overlay
    - Title text with stroke
    - Automatic text wrapping

    Example:
        >>> generator = ThumbnailGenerator()
        >>> thumbnail = await generator.generate(
        ...     title="Amazing Video Title",
        ...     background=visual_asset,
        ...     output_path=Path("/tmp/thumbnail.jpg"),
        ... )
    """

    def __init__(
        self,
        config: ThumbnailConfig | None = None,
        ffmpeg_wrapper: FFmpegWrapper | None = None,
    ) -> None:
        """Initialize ThumbnailGenerator.

        Args:
            config: Thumbnail configuration
            ffmpeg_wrapper: FFmpeg wrapper for video operations
        """
        self.config = config or ThumbnailConfig()
        self.ffmpeg = ffmpeg_wrapper or get_ffmpeg_wrapper()
        self._font_cache: dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

    async def generate(
        self,
        title: str,
        output_path: Path,
        background: VisualAsset | None = None,
        background_color: str = "#1a1a2e",
        config_override: ThumbnailConfig | None = None,
    ) -> Path:
        """Generate thumbnail image.

        Args:
            title: Video title
            output_path: Output path (without extension)
            background: Optional background visual asset
            background_color: Fallback background color
            config_override: Optional config to override instance config (from template)

        Returns:
            Path to generated thumbnail
        """
        # Use override config if provided, otherwise use instance config
        config = config_override or self.config

        output_path = output_path.with_suffix(".jpg")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width = config.width
        height = config.height

        # Create or load background
        if background and (background.path or background.url):
            bg_image = await self._load_background(background)
        else:
            rgb = self._hex_to_rgb(background_color)
            bg_image = Image.new("RGB", (width, height), rgb)

        # Resize background to target dimensions
        bg_image = self._resize_and_crop(bg_image, width, height)

        # Apply overlay
        bg_image = self._apply_overlay(bg_image, config)

        # Add title text
        bg_image = self._add_title(bg_image, title, config)

        # Save
        bg_image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=config.quality,
        )

        logger.info(f"Generated thumbnail: {output_path}")
        return output_path

    async def _load_background(self, asset: VisualAsset) -> Image.Image:
        """Load background image from asset.

        For video files, extracts a frame using FFmpeg.

        Args:
            asset: Visual asset

        Returns:
            PIL Image
        """
        if asset.path and asset.path.exists():
            # Check if it's a video file
            video_extensions = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
            if asset.path.suffix.lower() in video_extensions:
                return await self._extract_frame_from_video(asset.path)
            return Image.open(asset.path)

        if asset.url:
            async with httpx.AsyncClient() as client:
                response = await client.get(asset.url)
                response.raise_for_status()
                return Image.open(BytesIO(response.content))

        raise ValueError("Asset has no valid path or URL")

    async def _extract_frame_from_video(self, video_path: Path) -> Image.Image:
        """Extract a frame from video using FFmpeg SDK.

        Extracts a frame from 1 second into the video for better content.

        Args:
            video_path: Path to video file

        Returns:
            PIL Image of extracted frame
        """
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            stream = self.ffmpeg.extract_frame(
                video_path=video_path,
                output_path=tmp_path,
                seek_seconds=1.0,
                quality=2,
            )
            await self.ffmpeg.run(stream)
            return Image.open(tmp_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def _resize_and_crop(
        self,
        image: Image.Image,
        target_width: int,
        target_height: int,
    ) -> Image.Image:
        """Resize and crop image to target dimensions.

        Uses center crop to maintain aspect ratio.

        Args:
            image: Source image
            target_width: Target width
            target_height: Target height

        Returns:
            Resized image
        """
        # Calculate aspect ratios
        target_ratio = target_width / target_height
        source_ratio = image.width / image.height

        if source_ratio > target_ratio:
            # Source is wider, fit height and crop width
            new_height = target_height
            new_width = int(new_height * source_ratio)
        else:
            # Source is taller, fit width and crop height
            new_width = target_width
            new_height = int(new_width / source_ratio)

        # Resize
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Center crop
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        right = left + target_width
        bottom = top + target_height

        return image.crop((left, top, right, bottom))

    def _apply_overlay(self, image: Image.Image, config: ThumbnailConfig) -> Image.Image:
        """Apply semi-transparent overlay.

        Args:
            image: Source image
            config: Thumbnail configuration

        Returns:
            Image with overlay
        """
        # Convert to RGBA
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Create overlay
        overlay_color = self._hex_to_rgb(config.overlay_color)
        alpha = int(config.overlay_opacity * 255)

        overlay = Image.new("RGBA", image.size, (*overlay_color, alpha))

        # Composite
        return Image.alpha_composite(image, overlay)

    def _add_title(
        self,
        image: Image.Image,
        title: str,
        config: ThumbnailConfig,
    ) -> Image.Image:
        """Add title text to image.

        Args:
            image: Source image
            title: Title text
            config: Thumbnail configuration

        Returns:
            Image with title
        """
        draw = ImageDraw.Draw(image)

        # Load font
        font = self._get_font(config.title_font, config.title_size)

        # Wrap text
        wrapped = self._wrap_text(title, font, image.width - 2 * config.padding, config)

        # Calculate text position
        text_bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        if config.text_position == "center":
            x = (image.width - text_width) // 2
            y = (image.height - text_height) // 2
        else:  # bottom
            x = (image.width - text_width) // 2
            y = image.height - text_height - config.padding

        # Draw stroke (text outline)
        stroke_color = self._hex_to_rgb(config.title_stroke_color)
        stroke_width = config.title_stroke_width

        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.multiline_text(
                            (x + dx, y + dy),
                            wrapped,
                            font=font,
                            fill=stroke_color,
                            align="center",
                        )

        # Draw main text
        text_color = self._hex_to_rgb(config.title_color)
        draw.multiline_text(
            (x, y),
            wrapped,
            font=font,
            fill=text_color,
            align="center",
        )

        return image

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        config: ThumbnailConfig,
    ) -> str:
        """Wrap text to fit within max width.

        Args:
            text: Text to wrap
            font: Font to use
            max_width: Maximum width in pixels
            config: Thumbnail configuration

        Returns:
            Wrapped text with newlines
        """
        # Estimate characters per line
        avg_char_width = font.getlength("M")
        chars_per_line = max(1, int(max_width / avg_char_width))

        # Wrap text
        lines = textwrap.wrap(
            text,
            width=chars_per_line,
            break_long_words=True,
            break_on_hyphens=True,
        )

        # Limit to max lines
        if len(lines) > config.max_title_lines:
            lines = lines[: config.max_title_lines]
            lines[-1] = lines[-1][:-3] + "..."

        return "\n".join(lines)

    def _get_font(
        self,
        font_name: str,
        size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get or load font using fontconfig.

        Args:
            font_name: Font name or fontconfig query
            size: Font size

        Returns:
            PIL Font
        """
        cache_key = f"{font_name}_{size}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # Use fontconfig to find the font path
        font_path = find_font_by_name(font_name)

        try:
            font = ImageFont.truetype(font_path, size)
            self._font_cache[cache_key] = font
            logger.debug(f"Loaded font: {font_path}")
            return font
        except OSError:
            logger.warning(f"Failed to load font: {font_path}, using default")

        # Ultimate fallback: default font
        default_font = ImageFont.load_default()
        self._font_cache[cache_key] = default_font
        return default_font

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


__all__ = ["ThumbnailGenerator"]
