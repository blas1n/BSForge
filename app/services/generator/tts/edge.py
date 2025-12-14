"""Edge TTS engine implementation.

Microsoft Edge TTS provides free, high-quality neural TTS with:
- Word-level timestamps via WordBoundary events
- Multiple Korean and English voices
- Speed, pitch, and volume controls
"""

import asyncio
import logging
from pathlib import Path

from app.services.generator.tts.base import (
    EDGE_TTS_VOICES_EN,
    EDGE_TTS_VOICES_KO,
    BaseTTSEngine,
    TTSConfig,
    TTSResult,
    VoiceInfo,
    WordTimestamp,
)

logger = logging.getLogger(__name__)


class EdgeTTSEngine(BaseTTSEngine):
    """Edge TTS engine using Microsoft Edge's neural voices.

    Features:
    - Free to use
    - High-quality neural voices
    - Word-level timestamps
    - Multiple language support

    Example:
        >>> engine = EdgeTTSEngine()
        >>> config = TTSConfig(voice_id="ko-KR-InJoonNeural", speed=1.1)
        >>> result = await engine.synthesize("안녕하세요", config, Path("/tmp/audio"))
        >>> print(result.duration_seconds)
        1.5
    """

    def __init__(self) -> None:
        """Initialize EdgeTTSEngine."""
        self._voices: dict[str, VoiceInfo] = {
            **EDGE_TTS_VOICES_KO,
            **EDGE_TTS_VOICES_EN,
        }

    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
        output_path: Path,
    ) -> TTSResult:
        """Synthesize speech using Edge TTS.

        Args:
            text: Text to synthesize
            config: TTS configuration
            output_path: Path to save audio file (without extension)

        Returns:
            TTSResult with audio path and word timestamps

        Raises:
            ValueError: If voice_id is invalid
            RuntimeError: If synthesis fails
        """
        import edge_tts

        if config.voice_id not in self._voices:
            logger.warning(f"Voice {config.voice_id} not in predefined list, using anyway")

        # Build output path with extension
        audio_path = output_path.with_suffix(f".{config.output_format}")
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert speed to Edge TTS rate format
        rate_str = self._speed_to_rate_string(config.speed)
        pitch_str = self._pitch_to_string(config.pitch)
        volume_str = self._volume_to_string(config.volume)

        logger.info(
            f"Synthesizing with Edge TTS: voice={config.voice_id}, "
            f"rate={rate_str}, pitch={pitch_str}"
        )

        # Create communicator
        communicate = edge_tts.Communicate(
            text=text,
            voice=config.voice_id,
            rate=rate_str,
            pitch=pitch_str,
            volume=volume_str,
        )

        # Collect audio and timestamps
        word_timestamps: list[WordTimestamp] = []

        with open(audio_path, "wb") as f:
            async for message in communicate.stream():
                if message["type"] == "audio":
                    f.write(message["data"])
                elif message["type"] == "WordBoundary":
                    # Extract word timing
                    word = message.get("text", "")
                    offset_ns = message.get("offset", 0)  # 100-nanosecond units
                    duration_ns = message.get("duration", 0)

                    # Convert to seconds
                    start = offset_ns / 10_000_000
                    end = start + (duration_ns / 10_000_000)

                    if word.strip():
                        word_timestamps.append(
                            WordTimestamp(
                                word=word.strip(),
                                start=start,
                                end=end,
                            )
                        )

        # Get actual audio duration
        duration = await self.get_audio_duration(audio_path)

        logger.info(
            f"Synthesis complete: {audio_path}, duration={duration:.2f}s, "
            f"words={len(word_timestamps)}"
        )

        return TTSResult(
            audio_path=audio_path,
            duration_seconds=duration,
            word_timestamps=word_timestamps if word_timestamps else None,
            format=config.output_format,
        )

    def get_available_voices(
        self,
        language: str | None = None,
    ) -> list[VoiceInfo]:
        """Get available Edge TTS voices.

        Args:
            language: Optional language filter (e.g., "ko", "ko-KR", "en")

        Returns:
            List of matching voices
        """
        if language is None:
            return list(self._voices.values())

        # Normalize language code
        lang_prefix = language.lower().split("-")[0]

        return [
            voice
            for voice in self._voices.values()
            if voice.language.lower().startswith(lang_prefix)
        ]

    async def get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds

        Raises:
            RuntimeError: If ffprobe fails
        """
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            raise RuntimeError(f"ffprobe failed: {error_msg}")

        duration_str = stdout.decode().strip()
        return float(duration_str)

    def _speed_to_rate_string(self, speed: float) -> str:
        """Convert speed multiplier to Edge TTS rate string.

        Args:
            speed: Speed multiplier (1.0 = normal)

        Returns:
            Rate string (e.g., "+20%", "-10%")
        """
        percentage = int((speed - 1.0) * 100)
        if percentage >= 0:
            return f"+{percentage}%"
        return f"{percentage}%"

    def _pitch_to_string(self, pitch: int) -> str:
        """Convert pitch adjustment to Edge TTS pitch string.

        Args:
            pitch: Pitch adjustment in Hz

        Returns:
            Pitch string (e.g., "+10Hz", "-5Hz")
        """
        if pitch >= 0:
            return f"+{pitch}Hz"
        return f"{pitch}Hz"

    def _volume_to_string(self, volume: int) -> str:
        """Convert volume adjustment to Edge TTS volume string.

        Args:
            volume: Volume adjustment

        Returns:
            Volume string (e.g., "+10%", "-5%")
        """
        if volume >= 0:
            return f"+{volume}%"
        return f"{volume}%"


__all__ = ["EdgeTTSEngine"]
