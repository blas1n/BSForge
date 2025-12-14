"""ElevenLabs TTS engine implementation.

ElevenLabs provides premium, high-quality AI voices with:
- Natural-sounding speech
- Multilingual support
- Voice cloning capabilities
- Requires Whisper for word-level timestamps
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.services.generator.tts.base import (
    BaseTTSEngine,
    TTSConfig,
    TTSResult,
    VoiceInfo,
    WordTimestamp,
)

logger = logging.getLogger(__name__)


class ElevenLabsEngine(BaseTTSEngine):
    """ElevenLabs TTS engine for high-quality speech synthesis.

    Features:
    - Premium AI voices
    - Natural intonation and emotion
    - Multilingual support
    - Uses Whisper for word timestamps (not native)

    Note:
        Requires ELEVENLABS_API_KEY environment variable.
        Word timestamps are generated post-synthesis using Whisper.

    Example:
        >>> engine = ElevenLabsEngine(api_key="your-key")
        >>> config = TTSConfig(voice_id="21m00Tcm4TlvDq8ikWAM")
        >>> result = await engine.synthesize("Hello world", config, Path("/tmp/audio"))
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_id: str = "eleven_multilingual_v2",
    ) -> None:
        """Initialize ElevenLabsEngine.

        Args:
            api_key: ElevenLabs API key (or from ELEVENLABS_API_KEY env)
            model_id: ElevenLabs model ID
        """
        import os

        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self._api_key:
            logger.warning("ELEVENLABS_API_KEY not set, ElevenLabs TTS will not work")

        self._model_id = model_id
        self._voices_cache: list[VoiceInfo] | None = None

    async def synthesize(
        self,
        text: str,
        config: TTSConfig,
        output_path: Path,
    ) -> TTSResult:
        """Synthesize speech using ElevenLabs.

        Args:
            text: Text to synthesize
            config: TTS configuration
            output_path: Path to save audio file (without extension)

        Returns:
            TTSResult with audio path and word timestamps

        Raises:
            RuntimeError: If API key not set or synthesis fails
        """
        if not self._api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")

        from elevenlabs import AsyncElevenLabs

        # Build output path
        audio_path = output_path.with_suffix(f".{config.output_format}")
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Synthesizing with ElevenLabs: voice={config.voice_id}")

        # Create client
        client = AsyncElevenLabs(api_key=self._api_key)

        # Convert speed to stability/similarity parameters
        # ElevenLabs doesn't have direct speed control; use voice settings
        voice_settings = self._get_voice_settings(config)

        # Generate audio
        audio_generator = await client.text_to_speech.convert(
            voice_id=config.voice_id,
            text=text,
            model_id=self._model_id,
            voice_settings=voice_settings,
            output_format=self._get_output_format(config.output_format),
        )

        # Write audio file
        with open(audio_path, "wb") as f:
            async for chunk in audio_generator:
                f.write(chunk)

        # Get duration
        duration = await self.get_audio_duration(audio_path)

        # Generate word timestamps using Whisper
        word_timestamps = await self._generate_timestamps_with_whisper(audio_path, text)

        logger.info(
            f"Synthesis complete: {audio_path}, duration={duration:.2f}s, "
            f"words={len(word_timestamps) if word_timestamps else 0}"
        )

        return TTSResult(
            audio_path=audio_path,
            duration_seconds=duration,
            word_timestamps=word_timestamps,
            format=config.output_format,
        )

    def get_available_voices(
        self,
        language: str | None = None,
    ) -> list[VoiceInfo]:
        """Get available ElevenLabs voices.

        Note:
            This returns cached voices. Call refresh_voices() to update.

        Args:
            language: Optional language filter (not fully supported)

        Returns:
            List of available voices
        """
        if self._voices_cache is None:
            # Return some default voices
            return [
                VoiceInfo(
                    voice_id="21m00Tcm4TlvDq8ikWAM",
                    name="Rachel",
                    language="en",
                    gender="female",
                    description="Calm and natural female voice",
                ),
                VoiceInfo(
                    voice_id="AZnzlk1XvdvUeBnXmlld",
                    name="Domi",
                    language="en",
                    gender="female",
                    description="Strong and confident female voice",
                ),
                VoiceInfo(
                    voice_id="EXAVITQu4vr4xnSDxMaL",
                    name="Bella",
                    language="en",
                    gender="female",
                    description="Soft and gentle female voice",
                ),
                VoiceInfo(
                    voice_id="ErXwobaYiN019PkySvjV",
                    name="Antoni",
                    language="en",
                    gender="male",
                    description="Well-rounded male voice",
                ),
                VoiceInfo(
                    voice_id="VR6AewLTigWG4xSOukaG",
                    name="Arnold",
                    language="en",
                    gender="male",
                    description="Crisp and confident male voice",
                ),
            ]

        return self._voices_cache

    async def get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration using ffprobe.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
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

        return float(stdout.decode().strip())

    async def _generate_timestamps_with_whisper(
        self,
        audio_path: Path,
        original_text: str,
    ) -> list[WordTimestamp] | None:
        """Generate word timestamps using Whisper.

        Args:
            audio_path: Path to audio file
            original_text: Original text for reference

        Returns:
            List of word timestamps or None if failed
        """
        try:
            import whisper

            # Load model (cached after first load)
            model = whisper.load_model("base")

            # Transcribe with word timestamps
            result = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language=self._detect_language(original_text),
            )

            timestamps: list[WordTimestamp] = []

            # Extract word-level timestamps
            for segment in result.get("segments", []):
                for word_info in segment.get("words", []):
                    word = word_info.get("word", "").strip()
                    if word:
                        timestamps.append(
                            WordTimestamp(
                                word=word,
                                start=word_info.get("start", 0.0),
                                end=word_info.get("end", 0.0),
                            )
                        )

            return timestamps if timestamps else None

        except ImportError:
            logger.warning("Whisper not installed, skipping timestamp generation")
            return None
        except Exception as e:
            logger.warning(f"Whisper timestamp generation failed: {e}")
            return None

    def _get_voice_settings(self, config: TTSConfig) -> dict[str, Any]:
        """Get ElevenLabs voice settings from config.

        Args:
            config: TTS configuration

        Returns:
            Voice settings dict
        """
        # Map speed to stability/similarity
        # Faster speech typically means less stable
        stability = 0.5
        similarity_boost = 0.75

        # Adjust based on speed (higher speed = slightly less stable)
        if config.speed > 1.0:
            stability = max(0.3, stability - (config.speed - 1.0) * 0.2)
        elif config.speed < 1.0:
            stability = min(0.8, stability + (1.0 - config.speed) * 0.2)

        return {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": 0.0,
            "use_speaker_boost": True,
        }

    def _get_output_format(self, format: str) -> str:
        """Get ElevenLabs output format string.

        Args:
            format: Desired format (mp3, wav, ogg)

        Returns:
            ElevenLabs format string
        """
        format_map = {
            "mp3": "mp3_44100_128",
            "wav": "pcm_44100",
            "ogg": "mp3_44100_128",  # Fallback to mp3
        }
        return format_map.get(format, "mp3_44100_128")

    def _detect_language(self, text: str) -> str:
        """Detect language from text.

        Args:
            text: Text to analyze

        Returns:
            Language code for Whisper
        """
        # Simple heuristic: check for Korean characters
        korean_pattern = any("\uac00" <= char <= "\ud7a3" for char in text)
        return "ko" if korean_pattern else "en"


__all__ = ["ElevenLabsEngine"]
