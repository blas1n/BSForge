"""Video template configuration models.

This module defines Pydantic models for video style templates that can be
configured via YAML files. Templates support inheritance via the 'extends' field.

Example usage:
    ```yaml
    # config/templates/korean_viral.yaml
    name: korean_viral
    extends: minimal
    layout:
      title_overlay:
        enabled: true
    ```
"""

from typing import Literal

from pydantic import BaseModel, Field


class TitleOverlayConfig(BaseModel):
    """Configuration for the title overlay at the top of the video.

    This is commonly used in "viral shorts" style videos where
    a hook/title is displayed prominently at the top.
    """

    enabled: bool = True
    font_name: str = "Pretendard-Bold"
    font_size: int = Field(default=56, ge=12, le=144)
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = Field(default=2, ge=0, le=10)
    background_enabled: bool = True
    background_color: str = "#000000"
    background_opacity: float = Field(default=0.7, ge=0.0, le=1.0)
    position_y: int = Field(default=100, ge=0, le=500)
    max_width_ratio: float = Field(default=0.9, ge=0.5, le=1.0)
    line_spacing: float = Field(default=1.2, ge=1.0, le=2.0)


class FrameLayoutConfig(BaseModel):
    """Frame layout configuration for "양산형 쇼츠" style.

    Creates a frame with:
    - Top area: Title/hook text
    - Center area: Image/video content (smaller, in a frame)
    - Bottom area: Subtitles
    - Background: Solid color or gradient
    """

    enabled: bool = False
    background_color: str = "#1a1a2e"  # Dark blue-ish background
    background_gradient: bool = False
    gradient_top_color: str = "#1a1a2e"
    gradient_bottom_color: str = "#16213e"

    # Content frame (center image area)
    content_width_ratio: float = Field(
        default=0.85,
        ge=0.5,
        le=1.0,
        description="Width of content area relative to screen (0.85 = 85%)",
    )
    content_height_ratio: float = Field(
        default=0.5,
        ge=0.3,
        le=0.7,
        description="Height of content area relative to screen (0.5 = 50%)",
    )
    content_y_offset: int = Field(
        default=350,
        ge=100,
        le=800,
        description="Y offset from top for content area",
    )
    content_border_enabled: bool = True
    content_border_color: str = "#ffffff"
    content_border_width: int = Field(default=4, ge=0, le=20)
    content_border_radius: int = Field(default=20, ge=0, le=50)


class LayoutConfig(BaseModel):
    """Layout configuration for video elements.

    Controls the positioning of title overlay, subtitles, and frame layout.
    """

    title_overlay: TitleOverlayConfig | None = None
    subtitle_position: Literal["top", "center", "bottom"] = "center"
    subtitle_margin_ratio: float = Field(
        default=0.5,
        ge=0.1,
        le=0.9,
        description="Vertical position ratio (0.15=bottom, 0.5=center, 0.85=top)",
    )
    # Frame layout for "양산형" style
    frame: FrameLayoutConfig = Field(default_factory=FrameLayoutConfig)


class SubtitleTemplateConfig(BaseModel):
    """Subtitle style configuration.

    Controls font, colors, and animation effects for subtitles.
    """

    font_name: str = "Pretendard"
    font_size: int = Field(default=72, ge=12, le=144)
    bold: bool = True

    # Colors (hex format)
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = Field(default=4, ge=0, le=10)
    highlight_color: str = "#FFFF00"

    # Background
    background_enabled: bool = False
    background_color: str = "#000000"
    background_opacity: float = Field(default=0.0, ge=0.0, le=1.0)

    # Animation
    fade_in_ms: int = Field(default=200, ge=0, le=1000)
    fade_out_ms: int = Field(default=100, ge=0, le=1000)
    karaoke_enabled: bool = True

    # Text layout
    max_chars_per_line: int = Field(default=20, ge=10, le=50)
    max_lines: int = Field(default=2, ge=1, le=4)


class VisualEffectsConfig(BaseModel):
    """Visual effects configuration.

    Controls Ken Burns effect, transitions, and color grading.
    """

    # Ken Burns zoom effect
    ken_burns_enabled: bool = True
    ken_burns_zoom_speed: float = Field(
        default=0.0005,
        ge=0.0,
        le=0.01,
        description="Zoom speed per frame (0.0005 = subtle)",
    )
    ken_burns_start_scale: float = Field(
        default=1.15,
        ge=1.0,
        le=2.0,
        description="Starting scale for zoom-out effect",
    )

    # Transitions
    transition_type: Literal["none", "fade", "flash", "crossfade"] = "flash"
    transition_duration: float = Field(default=0.15, ge=0.0, le=2.0)

    # Segment timing
    segment_duration: float = Field(
        default=2.5,
        ge=1.0,
        le=10.0,
        description="Duration of each visual segment in seconds",
    )

    # Color grading
    color_grading_enabled: bool = True
    brightness: float = Field(default=0.05, ge=-0.5, le=0.5)
    contrast: float = Field(default=1.1, ge=0.5, le=2.0)
    saturation: float = Field(default=1.2, ge=0.0, le=2.0)
    warmth: float = Field(
        default=0.1,
        ge=-0.5,
        le=0.5,
        description="Orange/warm tone adjustment",
    )


class AudioTemplateConfig(BaseModel):
    """Audio configuration for the video."""

    bgm_volume: float = Field(default=0.1, ge=0.0, le=1.0)
    tts_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    normalize_audio: bool = True


class VideoTemplateConfig(BaseModel):
    """Complete video style template configuration.

    Templates can inherit from other templates using the 'extends' field.
    Child template values override parent values (deep merge).

    Attributes:
        name: Unique template identifier
        extends: Name of parent template to inherit from
        description: Human-readable description
        layout: Layout and positioning settings
        subtitle: Subtitle style settings
        visual_effects: Visual effects settings
        audio: Audio settings
    """

    name: str
    extends: str | None = None
    description: str = ""

    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    subtitle: SubtitleTemplateConfig = Field(default_factory=SubtitleTemplateConfig)
    visual_effects: VisualEffectsConfig = Field(default_factory=VisualEffectsConfig)
    audio: AudioTemplateConfig = Field(default_factory=AudioTemplateConfig)
