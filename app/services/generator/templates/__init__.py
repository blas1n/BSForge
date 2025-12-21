"""ASS subtitle template loader.

This module provides template loading and rendering for ASS subtitle generation.
Templates are stored as external files to avoid hardcoding and line length issues.
"""

from dataclasses import dataclass
from pathlib import Path
from string import Template

from app.core.logging import get_logger

logger = get_logger(__name__)

# Template directory path
TEMPLATE_DIR = Path(__file__).parent


@dataclass
class ASSStyleParams:
    """Parameters for ASS style definition.

    Attributes:
        name: Style name (e.g., "Default", "Highlight", "Persona")
        font_name: Font family name
        font_size: Font size in pixels
        primary_color: Primary text color (&HAABBGGRR format)
        secondary_color: Secondary color for karaoke
        outline_color: Outline/border color
        back_color: Background/shadow color
        bold: Bold flag (0 or 1)
        italic: Italic flag (0 or 1)
        underline: Underline flag (0 or 1)
        strikeout: Strikeout flag (0 or 1)
        scale_x: Horizontal scale percentage
        scale_y: Vertical scale percentage
        spacing: Letter spacing
        angle: Rotation angle
        border_style: Border style (1=outline, 3=background box)
        outline: Outline width
        shadow: Shadow depth
        alignment: Text alignment (numpad layout)
        margin_l: Left margin
        margin_r: Right margin
        margin_v: Vertical margin
        encoding: Character encoding (1=default)
    """

    name: str
    font_name: str
    font_size: int
    primary_color: str
    secondary_color: str = "&H00000000"
    outline_color: str = "&H00000000"
    back_color: str = "&H00000000"
    bold: int = 0
    italic: int = 0
    underline: int = 0
    strikeout: int = 0
    scale_x: int = 100
    scale_y: int = 100
    spacing: int = 0
    angle: int = 0
    border_style: int = 1
    outline: int = 2
    shadow: int = 0
    alignment: int = 2
    margin_l: int = 20
    margin_r: int = 20
    margin_v: int = 50
    encoding: int = 1


@dataclass
class ASSDialogueParams:
    """Parameters for ASS dialogue line.

    Attributes:
        layer: Layer number (0 for default)
        start: Start time (H:MM:SS.CC format)
        end: End time (H:MM:SS.CC format)
        style: Style name to use
        name: Actor name (usually empty)
        margin_l: Left margin override (0 for default)
        margin_r: Right margin override (0 for default)
        margin_v: Vertical margin override (0 for default)
        effect: Effect name (usually empty)
        text: Subtitle text (may include ASS tags)
    """

    layer: int = 0
    start: str = "0:00:00.00"
    end: str = "0:00:00.00"
    style: str = "Default"
    name: str = ""
    margin_l: int = 0
    margin_r: int = 0
    margin_v: int = 0
    effect: str = ""
    text: str = ""


class ASSTemplateLoader:
    """Load and render ASS subtitle templates.

    Usage:
        >>> loader = ASSTemplateLoader()
        >>> style = ASSStyleParams(name="Default", font_name="Arial", ...)
        >>> header = loader.render_header(title="My Subtitles", styles=[style])
        >>> dialogue = loader.render_dialogue(start="0:00:01.00", end="0:00:03.00", text="Hello")
    """

    def __init__(self) -> None:
        """Initialize template loader."""
        self._base_template: str | None = None
        self._style_template: str | None = None
        self._dialogue_template: str | None = None

    @property
    def base_template(self) -> str:
        """Load base ASS template."""
        if self._base_template is None:
            template_path = TEMPLATE_DIR / "ass_base.ass"
            self._base_template = template_path.read_text(encoding="utf-8")
        return self._base_template

    @property
    def style_template(self) -> str:
        """Load style line template."""
        if self._style_template is None:
            template_path = TEMPLATE_DIR / "ass_style.txt"
            self._style_template = template_path.read_text(encoding="utf-8").strip()
        return self._style_template

    @property
    def dialogue_template(self) -> str:
        """Load dialogue line template."""
        if self._dialogue_template is None:
            template_path = TEMPLATE_DIR / "ass_dialogue.txt"
            self._dialogue_template = template_path.read_text(encoding="utf-8").strip()
        return self._dialogue_template

    def render_style(self, params: ASSStyleParams) -> str:
        """Render a single style line.

        Args:
            params: Style parameters

        Returns:
            Formatted style line
        """
        template = Template(self.style_template)
        return template.safe_substitute(
            name=params.name,
            font_name=params.font_name,
            font_size=params.font_size,
            primary_color=params.primary_color,
            secondary_color=params.secondary_color,
            outline_color=params.outline_color,
            back_color=params.back_color,
            bold=params.bold,
            italic=params.italic,
            underline=params.underline,
            strikeout=params.strikeout,
            scale_x=params.scale_x,
            scale_y=params.scale_y,
            spacing=params.spacing,
            angle=params.angle,
            border_style=params.border_style,
            outline=params.outline,
            shadow=params.shadow,
            alignment=params.alignment,
            margin_l=params.margin_l,
            margin_r=params.margin_r,
            margin_v=params.margin_v,
            encoding=params.encoding,
        )

    def render_header(
        self,
        title: str,
        styles: list[ASSStyleParams],
        play_res_x: int = 1080,
        play_res_y: int = 1920,
    ) -> str:
        """Render ASS header with styles.

        Args:
            title: Subtitle title
            styles: List of style definitions
            play_res_x: Playback resolution width
            play_res_y: Playback resolution height

        Returns:
            Complete ASS header string
        """
        # Render all styles
        style_lines = [self.render_style(s) for s in styles]
        styles_str = "\n".join(style_lines)

        # Render header
        template = Template(self.base_template)
        return template.safe_substitute(
            title=title,
            play_res_x=play_res_x,
            play_res_y=play_res_y,
            styles=styles_str,
        )

    def render_dialogue(self, params: ASSDialogueParams) -> str:
        """Render a single dialogue line.

        Args:
            params: Dialogue parameters

        Returns:
            Formatted dialogue line
        """
        template = Template(self.dialogue_template)
        return template.safe_substitute(
            layer=params.layer,
            start=params.start,
            end=params.end,
            style=params.style,
            name=params.name,
            margin_l=params.margin_l,
            margin_r=params.margin_r,
            margin_v=params.margin_v,
            effect=params.effect,
            text=params.text,
        )

    def clear_cache(self) -> None:
        """Clear cached templates."""
        self._base_template = None
        self._style_template = None
        self._dialogue_template = None
        logger.debug("Cleared ASS template cache")


__all__ = [
    "ASSDialogueParams",
    "ASSStyleParams",
    "ASSTemplateLoader",
]
