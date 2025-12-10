"""Persona configuration models."""

from typing import Literal

from pydantic import BaseModel, Field


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


class PersonaConfig(BaseModel):
    """Persona configuration.

    Attributes:
        name: Persona name
        tagline: Persona tagline
        voice: Voice configuration
        communication: Communication style
        perspective: Perspective and values
    """

    name: str = Field(..., min_length=1, max_length=50, description="Persona name")
    tagline: str = Field(..., min_length=1, max_length=100, description="Persona tagline")
    voice: VoiceConfig
    communication: CommunicationStyle
    perspective: Perspective
