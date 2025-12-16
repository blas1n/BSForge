"""Thumbnail generation service.

Generates YouTube thumbnail images using PIL.
"""

import logging
import subprocess
import tempfile
import textwrap
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.config.video import ThumbnailConfig
from app.services.generator.visual.base import VisualAsset

logger = logging.getLogger(__name__)


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

    def __init__(self, config: ThumbnailConfig | None = None) -> None:
        """Initialize ThumbnailGenerator.

        Args:
            config: Thumbnail configuration
        """
        self.config = config or ThumbnailConfig()
        self._font_cache: dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

    async def generate(
        self,
        title: str,
        output_path: Path,
        background: VisualAsset | None = None,
        background_color: str = "#1a1a2e",
    ) -> Path:
        """Generate thumbnail image.

        Args:
            title: Video title
            output_path: Output path (without extension)
            background: Optional background visual asset
            background_color: Fallback background color

        Returns:
            Path to generated thumbnail
        """
        output_path = output_path.with_suffix(".jpg")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width = self.config.width
        height = self.config.height

        # Create or load background
        if background and (background.path or background.url):
            bg_image = await self._load_background(background)
        else:
            rgb = self._hex_to_rgb(background_color)
            bg_image = Image.new("RGB", (width, height), rgb)

        # Resize background to target dimensions
        bg_image = self._resize_and_crop(bg_image, width, height)

        # Apply overlay
        bg_image = self._apply_overlay(bg_image)

        # Add title text
        bg_image = self._add_title(bg_image, title)

        # Save
        bg_image.convert("RGB").save(
            output_path,
            "JPEG",
            quality=self.config.quality,
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
                return self._extract_frame_from_video(asset.path)
            return Image.open(asset.path)

        if asset.url:
            async with httpx.AsyncClient() as client:
                response = await client.get(asset.url)
                response.raise_for_status()
                return Image.open(BytesIO(response.content))

        raise ValueError("Asset has no valid path or URL")

    def _extract_frame_from_video(self, video_path: Path) -> Image.Image:
        """Extract a frame from video using FFmpeg.

        Extracts a frame from 1 second into the video for better content.

        Args:
            video_path: Path to video file

        Returns:
            PIL Image of extracted frame
        """
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                "1",  # Seek to 1 second
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                "2",
                str(tmp_path),
            ]
            subprocess.run(cmd, capture_output=True, check=True)
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

    def _apply_overlay(self, image: Image.Image) -> Image.Image:
        """Apply semi-transparent overlay.

        Args:
            image: Source image

        Returns:
            Image with overlay
        """
        # Convert to RGBA
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        # Create overlay
        overlay_color = self._hex_to_rgb(self.config.overlay_color)
        alpha = int(self.config.overlay_opacity * 255)

        overlay = Image.new("RGBA", image.size, (*overlay_color, alpha))

        # Composite
        return Image.alpha_composite(image, overlay)

    def _add_title(
        self,
        image: Image.Image,
        title: str,
    ) -> Image.Image:
        """Add title text to image.

        Args:
            image: Source image
            title: Title text

        Returns:
            Image with title
        """
        draw = ImageDraw.Draw(image)

        # Load font
        font = self._get_font(self.config.title_font, self.config.title_size)

        # Wrap text
        wrapped = self._wrap_text(title, font, image.width - 2 * self.config.padding)

        # Calculate text position
        text_bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        if self.config.text_position == "center":
            x = (image.width - text_width) // 2
            y = (image.height - text_height) // 2
        else:  # bottom
            x = (image.width - text_width) // 2
            y = image.height - text_height - self.config.padding

        # Draw stroke (text outline)
        stroke_color = self._hex_to_rgb(self.config.title_stroke_color)
        stroke_width = self.config.title_stroke_width

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
        text_color = self._hex_to_rgb(self.config.title_color)
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
    ) -> str:
        """Wrap text to fit within max width.

        Args:
            text: Text to wrap
            font: Font to use
            max_width: Maximum width in pixels

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
        if len(lines) > self.config.max_title_lines:
            lines = lines[: self.config.max_title_lines]
            lines[-1] = lines[-1][:-3] + "..."

        return "\n".join(lines)

    def _get_font(
        self,
        font_name: str,
        size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Get or load font with Korean support.

        Args:
            font_name: Font name
            size: Font size

        Returns:
            PIL Font
        """
        import os

        cache_key = f"{font_name}_{size}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # Priority order for Korean-supporting fonts
        korean_font_paths = [
            # User-installed Noto Sans CJK (Korean)
            os.path.expanduser("~/.local/share/fonts/NotoSansKR-Bold.ttf"),
            os.path.expanduser("~/.local/share/fonts/NotoSansKR-Regular.ttf"),
            # System Noto Sans CJK
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            # Nanum fonts (common Korean fonts)
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        ]

        # Try Korean fonts first
        for path in korean_font_paths:
            try:
                font = ImageFont.truetype(path, size)
                self._font_cache[cache_key] = font
                logger.info(f"Using Korean font: {path}")
                return font
            except OSError:
                continue

        # Try to load the specified font
        font_paths = [
            f"/usr/share/fonts/truetype/{font_name}.ttf",
            f"/usr/share/fonts/{font_name}.ttf",
            f"/System/Library/Fonts/{font_name}.ttf",
            f"C:/Windows/Fonts/{font_name}.ttf",
        ]

        for path in font_paths:
            try:
                font = ImageFont.truetype(path, size)
                self._font_cache[cache_key] = font
                return font
            except OSError:
                continue

        # Try common fallback fonts
        fallback_fonts = [
            "DejaVuSans-Bold",
            "DejaVuSans",
            "Arial",
            "Helvetica",
        ]

        for fallback in fallback_fonts:
            for ext in [".ttf", ".otf"]:
                try:
                    font = ImageFont.truetype(fallback + ext, size)
                    self._font_cache[cache_key] = font
                    logger.warning(f"Using fallback font: {fallback}")
                    return font
                except OSError:
                    continue

        # Ultimate fallback: default font
        # In modern Pillow (10+), load_default() returns FreeTypeFont
        logger.warning("Using default PIL font (Korean may not render correctly)")
        default_font = ImageFont.load_default()
        # Cache the default font as well for consistency
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
