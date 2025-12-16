"""Persona configuration models."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.scene import TransitionType


class VoiceSettings(BaseModel):
    """Voice synthesis settings.

    Attributes:
        speed: Speech speed multiplier (0.5-2.0)
        pitch: Pitch adjustment (-20 to 20)
    """

    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed")
    pitch: int = Field(default=0, ge=-20, le=20, description="Pitch adjustment")


class VoiceConfig(BaseModel):
    """Voice configuration.

    Attributes:
        gender: Voice gender
        service: TTS service to use
        voice_id: Voice identifier for the service
        settings: Voice synthesis settings
    """

    gender: Literal["male", "female", "neutral"] = Field(..., description="Voice gender")
    service: Literal["edge-tts", "elevenlabs"] = Field(..., description="TTS service")
    voice_id: str = Field(..., description="Voice ID")
    settings: VoiceSettings = Field(default_factory=VoiceSettings)


class SpeechPatterns(BaseModel):
    """Speech pattern configuration.

    Attributes:
        sentence_endings: Common sentence ending patterns
        connectors: Connecting words/phrases
        emphasis_words: Words used for emphasis
    """

    sentence_endings: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    emphasis_words: list[str] = Field(default_factory=list)


class AvoidPatterns(BaseModel):
    """Patterns to avoid in speech.

    Attributes:
        words: Words to avoid
        styles: Speech styles to avoid
    """

    words: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)


class CommunicationStyle(BaseModel):
    """Communication style configuration.

    Attributes:
        tone: Overall tone
        formality: Formality level
        speech_patterns: Speech pattern preferences
        avoid_patterns: Patterns to avoid
    """

    tone: str = Field(..., description="Communication tone")
    formality: Literal["formal", "semi-formal", "casual"] = Field(
        ..., description="Formality level"
    )
    speech_patterns: SpeechPatterns = Field(default_factory=SpeechPatterns)
    avoid_patterns: AvoidPatterns = Field(default_factory=AvoidPatterns)


class Perspective(BaseModel):
    """Persona perspective and values.

    Attributes:
        approach: Content approach style
        core_values: Core values
        contrarian_views: Contrarian viewpoints
    """

    approach: Literal["practical", "analytical", "entertaining"] = Field(
        ..., description="Content approach"
    )
    core_values: list[str] = Field(default_factory=list)
    contrarian_views: list[str] = Field(default_factory=list)


class PersonaStyleConfig(BaseModel):
    """Visual style configuration for persona scenes.

    This config defines how COMMENTARY and REACTION scenes are visually
    differentiated from factual content scenes. Each channel can customize
    these settings to match their brand.

    Attributes:
        accent_color: Primary accent color for persona scenes (hex)
        secondary_color: Secondary color for emphasis (hex)
        subtitle_font: Font family for subtitles
        fact_to_opinion_transition: Transition effect when switching to opinion
        opinion_color_flash: Color for flash transition (defaults to accent_color)
        use_persona_border: Whether to show left border on persona scenes
        border_width: Width of left border in pixels
        overlay_opacity_neutral: Background overlay opacity for neutral scenes
        overlay_opacity_persona: Background overlay opacity for persona scenes
    """

    # Colors
    accent_color: str = Field(
        default="#FF6B6B",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Primary accent color (hex)",
    )
    secondary_color: str = Field(
        default="#4ECDC4",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Secondary color (hex)",
    )

    # Subtitle styling
    subtitle_font: str = Field(
        default="Pretendard Bold",
        description="Font family for subtitles",
    )

    # Transitions
    fact_to_opinion_transition: TransitionType = Field(
        default=TransitionType.FLASH,
        description="Transition effect for fact→opinion",
    )
    opinion_color_flash: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Flash color (defaults to accent_color if None)",
    )

    # Layout
    use_persona_border: bool = Field(
        default=True,
        description="Show left border on persona scenes",
    )
    border_width: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Border width in pixels",
    )

    # Overlay
    overlay_opacity_neutral: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Overlay opacity for neutral scenes",
    )
    overlay_opacity_persona: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Overlay opacity for persona scenes",
    )

    @property
    def flash_color(self) -> str:
        """Get flash color (opinion_color_flash or accent_color)."""
        return self.opinion_color_flash or self.accent_color


class PersonaConfig(BaseModel):
    """Persona configuration.

    Attributes:
        name: Persona name
        tagline: Persona tagline
        voice: Voice configuration
        communication: Communication style
        perspective: Perspective and values
        visual_style: Visual style for scene rendering
    """

    name: str = Field(..., min_length=1, max_length=50, description="Persona name")
    tagline: str = Field(..., min_length=1, max_length=100, description="Persona tagline")
    voice: VoiceConfig
    communication: CommunicationStyle
    perspective: Perspective
    visual_style: PersonaStyleConfig = Field(
        default_factory=PersonaStyleConfig,
        description="Visual style for scene rendering",
    )
