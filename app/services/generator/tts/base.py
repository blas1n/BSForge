"""Base TTS engine interface and data structures.

This module defines the abstract base class for TTS engines and
common data structures used across all TTS implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class WordTimestamp:
    """Word-level timing information.

    Attributes:
        word: The word text
        start: Start time in seconds
        end: End time in seconds
    """

    word: str
    start: float
    end: float

    def __post_init__(self) -> None:
        """Validate timestamp values."""
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time cannot be before start time")


@dataclass
class TTSResult:
    """Result of TTS synthesis.

    Attributes:
        audio_path: Path to the generated audio file
        duration_seconds: Total duration in seconds
        word_timestamps: Optional list of word-level timestamps
        sample_rate: Audio sample rate
        format: Audio format (mp3, wav, etc.)
    """

    audio_path: Path
    duration_seconds: float
    word_timestamps: list[WordTimestamp] | None = None
    sample_rate: int = 24000
    format: Literal["mp3", "wav", "ogg"] = "mp3"


@dataclass
class VoiceInfo:
    """Information about an available voice.

    Attributes:
        voice_id: Unique voice identifier
        name: Human-readable voice name
        language: Language code (e.g., "ko-KR", "en-US")
        gender: Voice gender
        description: Optional voice description
        is_neural: Whether it's a neural voice
        sample_url: Optional URL to voice sample
    """

    voice_id: str
    name: str
    language: str
    gender: Literal["male", "female", "neutral"]
    description: str | None = None
    is_neural: bool = True
    sample_url: str | None = None


@dataclass
class TTSConfig:
    """Configuration for TTS synthesis.

    Attributes:
        voice_id: Voice identifier to use
        speed: Speech rate multiplier (1.0 = normal)
        pitch: Pitch adjustment in Hz (0 = no change)
        volume: Volume adjustment (0 = no change)
        output_format: Output audio format
    """

    voice_id: str
    speed: float = 1.0
    pitch: int = 0
    volume: int = 0
    output_format: Literal["mp3", "wav", "ogg"] = "mp3"

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.5 <= self.speed <= 2.0:
            raise ValueError("Speed must be between 0.5 and 2.0")
        if not -50 <= self.pitch <= 50:
            raise ValueError("Pitch must be between -50 and 50")
        if not -50 <= self.volume <= 50:
            raise ValueError("Volume must be between -50 and 50")


# Korean voice constants for Edge TTS
EDGE_TTS_VOICES_KO: dict[str, VoiceInfo] = {
    "ko-KR-InJoonNeural": VoiceInfo(
        voice_id="ko-KR-InJoonNeural",
        name="인준",
        language="ko-KR",
        gender="male",
        description="자연스럽고 차분한 남성 목소리",
    ),
    "ko-KR-BongJinNeural": VoiceInfo(
        voice_id="ko-KR-BongJinNeural",
        name="봉진",
        language="ko-KR",
        gender="male",
        description="차분하고 신뢰감 있는 남성 목소리",
    ),
    "ko-KR-GookMinNeural": VoiceInfo(
        voice_id="ko-KR-GookMinNeural",
        name="국민",
        language="ko-KR",
        gender="male",
        description="밝고 활기찬 남성 목소리",
    ),
    "ko-KR-SunHiNeural": VoiceInfo(
        voice_id="ko-KR-SunHiNeural",
        name="선희",
        language="ko-KR",
        gender="female",
        description="자연스럽고 부드러운 여성 목소리",
    ),
    "ko-KR-JiMinNeural": VoiceInfo(
        voice_id="ko-KR-JiMinNeural",
        name="지민",
        language="ko-KR",
        gender="female",
        description="밝고 친근한 여성 목소리",
    ),
    "ko-KR-SeoHyeonNeural": VoiceInfo(
        voice_id="ko-KR-SeoHyeonNeural",
        name="서현",
        language="ko-KR",
        gender="female",
        description="차분하고 신뢰감 있는 여성 목소리",
    ),
    "ko-KR-YuJinNeural": VoiceInfo(
        voice_id="ko-KR-YuJinNeural",
        name="유진",
        language="ko-KR",
        gender="female",
        description="또렷하고 명확한 여성 목소리",
    ),
}

# English voice constants for Edge TTS
EDGE_TTS_VOICES_EN: dict[str, VoiceInfo] = {
    "en-US-AriaNeural": VoiceInfo(
        voice_id="en-US-AriaNeural",
        name="Aria",
        language="en-US",
        gender="female",
        description="Natural conversational female voice",
    ),
    "en-US-GuyNeural": VoiceInfo(
        voice_id="en-US-GuyNeural",
        name="Guy",
        language="en-US",
        gender="male",
        description="Natural conversational male voice",
    ),
    "en-US-JennyNeural": VoiceInfo(
        voice_id="en-US-JennyNeural",
        name="Jenny",
        language="en-US",
        gender="female",
        description="Friendly and warm female voice",
    ),
    "en-US-DavisNeural": VoiceInfo(
        voice_id="en-US-DavisNeural",
        name="Davis",
        language="en-US",
        gender="male",
        description="Professional male voice",
    ),
}


class BaseTTSEngine(ABC):
    """Abstract base class for TTS engines.

    All TTS implementations must inherit from this class and implement
    the required methods.
    """

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
        output_path: Path,
    ) -> TTSResult:
        """Synthesize speech from text.

        Args:
            text: Text to synthesize
            config: TTS configuration
            output_path: Path to save audio file (without extension)

        Returns:
            TTSResult with audio path and metadata
        """
        pass

    @abstractmethod
    def get_available_voices(
        self,
        language: str | None = None,
    ) -> list[VoiceInfo]:
        """Get available voices.

        Args:
            language: Optional language filter (e.g., "ko-KR", "en-US")

        Returns:
            List of available voices
        """
        pass

    @abstractmethod
    async def get_audio_duration(self, audio_path: Path) -> float:
        """Get duration of an audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        pass


__all__ = [
    "WordTimestamp",
    "TTSResult",
    "TTSConfig",
    "VoiceInfo",
    "BaseTTSEngine",
    "EDGE_TTS_VOICES_KO",
    "EDGE_TTS_VOICES_EN",
]
