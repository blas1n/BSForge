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

Korean Shorts Standard Layout (양산형 쇼츠):
    ┌──────────────────┐
    │  상단 헤드라인    │  ← 10~20% (키워드 컬러 + 흰색 설명)
    ├──────────────────┤
    │                  │
    │   메인 이미지     │  ← 60~70% (꽉 채움)
    │                  │
    ├──────────────────┤
    │  하단 자막        │  ← 15~25% (흰색, 외곽선)
    └──────────────────┘
"""

from typing import Literal

from pydantic import BaseModel, Field


class HeadlineLineConfig(BaseModel):
    """Configuration for a single headline line.

    Used in the 2-line headline structure common in Korean shorts:
    - Line 1: Keyword with accent color
    - Line 2: Description in white
    """

    color: str = Field(default="#FFFFFF", description="Text color (hex)")
    font_size: int = Field(default=72, ge=24, le=144)
    bold: bool = True
    outline_width: int = Field(default=4, ge=0, le=10)


class HeadlineConfig(BaseModel):
    """Configuration for 2-line headline at top of video.

    Korean shorts style - NO BACKGROUND, text directly on image:
    ┌──────────────────┐
    │  키워드 (컬러)    │  ← Line 1: accent color, bold
    │  설명 (흰색)      │  ← Line 2: white
    └──────────────────┘

    Key characteristics:
    - No background (배경 없이 이미지 위에 바로 텍스트)
    - Bold font with tight letter spacing (자간 좁게)
    - Line 1: 1-4 words, single accent color
    - Line 2: Hook/description in white
    """

    enabled: bool = True
    position_y_ratio: float = Field(
        default=0.10,
        ge=0.02,
        le=0.25,
        description="Y position as ratio of screen height (0.10 = 10% from top)",
    )

    # Line 1: Keyword (accent color) - e.g., "모아이 석상", "이집트 피라미드"
    line1: HeadlineLineConfig = Field(
        default_factory=lambda: HeadlineLineConfig(
            color="#FF69B4",  # Hot pink (like analysis examples)
            font_size=72,
            bold=True,
            outline_width=4,
        )
    )

    # Line 2: Description (white) - e.g., "어떻게 움직였을까?", "반짝반짝 눈이 부셔"
    line2: HeadlineLineConfig = Field(
        default_factory=lambda: HeadlineLineConfig(
            color="#FFFFFF",
            font_size=56,
            bold=True,
            outline_width=3,
        )
    )

    font_name: str = "Pretendard-Bold"
    outline_color: str = "#000000"
    line_spacing: float = Field(default=1.3, ge=1.0, le=2.0)
    letter_spacing: float = Field(
        default=-0.02,
        ge=-0.1,
        le=0.1,
        description="Letter spacing ratio (negative = tighter, 쇼츠 감성)",
    )
    max_width_ratio: float = Field(default=0.9, ge=0.5, le=1.0)

    # Shadow for better visibility on any background
    shadow_enabled: bool = True
    shadow_color: str = "#000000"
    shadow_offset: int = Field(default=3, ge=0, le=10)

    # Background for headline area (검은 배경)
    background_enabled: bool = False
    background_color: str = "#000000"
    background_opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    background_padding_x: int = Field(default=40, ge=0, le=100)
    background_padding_y: int = Field(default=30, ge=0, le=100)
    background_height_ratio: float = Field(
        default=0.18,
        ge=0.1,
        le=0.4,
        description="Height of background area as ratio of screen (0.18 = 18%)",
    )


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


class CaptionConfig(BaseModel):
    """Configuration for bottom caption (하단 자막).

    Korean shorts style:
    - Position: Center to bottom area
    - White text with black outline
    - Optional word emphasis (yellow/green highlight)
    - Short, declarative sentences
    """

    enabled: bool = True
    position_y_ratio: float = Field(
        default=0.82,
        ge=0.3,
        le=0.95,
        description="Y position as ratio (0.55 = center, 0.82 = bottom 18%)",
    )
    font_name: str = "Pretendard-Bold"
    font_size: int = Field(default=48, ge=24, le=200)
    primary_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width: int = Field(default=3, ge=0, le=10)

    # Emphasis for keywords (노랑/초록 강조)
    emphasis_enabled: bool = True
    emphasis_color: str = "#FFFF00"  # Yellow default

    # Text wrapping
    max_chars_per_line: int = Field(default=18, ge=5, le=30)
    max_lines: int = Field(default=2, ge=1, le=3)

    # Animation
    fade_in_ms: int = Field(default=100, ge=0, le=500)
    fade_out_ms: int = Field(default=80, ge=0, le=500)


class LayoutConfig(BaseModel):
    """Layout configuration for video elements.

    Korean Shorts Standard Layout (양산형 쇼츠):
    ┌──────────────────┐
    │  상단 헤드라인    │  ← headline (10~20%)
    ├──────────────────┤
    │                  │
    │   메인 이미지     │  ← fullscreen image (60~70%)
    │                  │
    ├──────────────────┤
    │  하단 자막        │  ← caption (15~25%)
    └──────────────────┘

    Controls the positioning of headline and caption overlays.
    """

    # 2-line headline at top (Korean shorts standard)
    headline: HeadlineConfig | None = None

    # Bottom caption for explanatory text
    caption: CaptionConfig | None = None

    subtitle_position: Literal["top", "center", "bottom"] = "bottom"
    subtitle_margin_ratio: float = Field(
        default=0.18,
        ge=0.1,
        le=0.9,
        description="Vertical position ratio (0.18=bottom 18%, for UI safe zone)",
    )

    # Frame layout for "양산형" style (optional, for framed content)
    frame: FrameLayoutConfig = Field(default_factory=FrameLayoutConfig)

    # Image fills entire screen (no frame) by default
    fullscreen_image: bool = Field(
        default=True,
        description="Image fills entire screen (이미지 꽉 채움)",
    )


class SubtitleTemplateConfig(BaseModel):
    """Subtitle style configuration.

    Controls font, colors, and animation effects for subtitles.
    """

    font_name: str = "Pretendard"
    font_size: int = Field(default=72, ge=12, le=200)
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
    max_chars_per_line: int = Field(default=20, ge=5, le=50)
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


class VisualPromptConfig(BaseModel):
    """Visual/image generation prompt guidelines.

    Used to guide AI image generation (DALL-E, etc.) and stock image search
    for optimal Korean shorts style visuals.
    """

    # Keywords to include in prompts
    include_keywords: list[str] = Field(
        default=[
            "vertical 9:16 composition",
            "cinematic lighting",
            "simple background",
            "center-focused subject",
            "high contrast",
            "realistic or semi-realistic style",
            "empty space at top and bottom for subtitles",
            "viral short-form video thumbnail style",
            "dramatic but clean",
            "clear silhouette",
            "slightly exaggerated lighting",
            "social media short video aesthetic",
            "easy to understand at a glance",
        ],
        description="Keywords to include in image generation prompts",
    )

    # Keywords to exclude (negative prompt)
    exclude_keywords: list[str] = Field(
        default=[
            "text",
            "subtitle",
            "logo",
            "watermark",
            "busy background",
            "cluttered composition",
            "multiple focal points",
            "low contrast",
            "blurry subject",
            "horizontal layout",
        ],
        description="Keywords for negative prompt / exclusion",
    )

    # Style presets
    style: Literal["realistic", "semi-realistic", "stylized", "anime"] = Field(
        default="realistic",
        description="Overall visual style",
    )

    def build_prompt_suffix(self) -> str:
        """Build suffix to append to image generation prompts."""
        return ", ".join(self.include_keywords)

    def build_negative_prompt(self) -> str:
        """Build negative prompt for AI image generation."""
        return ", ".join(self.exclude_keywords)


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
    visual_prompt: VisualPromptConfig = Field(default_factory=VisualPromptConfig)


__all__ = [
    "VideoTemplateConfig",
    "LayoutConfig",
    "HeadlineConfig",
    "HeadlineLineConfig",
    "CaptionConfig",
    "FrameLayoutConfig",
    "SubtitleTemplateConfig",
    "VisualEffectsConfig",
    "AudioTemplateConfig",
    "VisualPromptConfig",
]
