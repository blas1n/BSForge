"""TTS Engine Factory.

Factory pattern for creating and managing TTS engine instances.
"""

import logging
from typing import Literal

from app.config.video import TTSConfig as TTSConfigModel
from app.services.generator.tts.base import BaseTTSEngine
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.tts.elevenlabs import ElevenLabsEngine

logger = logging.getLogger(__name__)

TTSProvider = Literal["edge-tts", "elevenlabs"]


class TTSEngineFactory:
    """Factory for creating TTS engine instances.

    Implements singleton pattern for engine reuse and efficient resource management.

    Example:
        >>> factory = TTSEngineFactory()
        >>> edge_engine = factory.get_engine("edge-tts")
        >>> elevenlabs_engine = factory.get_engine("elevenlabs")
    """

    def __init__(
        self,
        config: TTSConfigModel | None = None,
        elevenlabs_api_key: str | None = None,
    ) -> None:
        """Initialize TTSEngineFactory.

        Args:
            config: Optional TTS configuration
            elevenlabs_api_key: Optional ElevenLabs API key
        """
        self._config = config or TTSConfigModel()
        self._elevenlabs_api_key = elevenlabs_api_key
        self._engines: dict[str, BaseTTSEngine] = {}

    def get_engine(self, provider: str | None = None) -> BaseTTSEngine:
        """Get or create a TTS engine instance.

        Args:
            provider: TTS provider ("edge-tts" or "elevenlabs")
                     If None, uses config default

        Returns:
            TTS engine instance

        Raises:
            ValueError: If provider is not supported
        """
        if provider is None:
            provider = self._config.provider

        if provider in self._engines:
            return self._engines[provider]

        logger.info(f"Creating TTS engine: {provider}")

        engine: BaseTTSEngine
        if provider == "edge-tts":
            engine = EdgeTTSEngine()
        elif provider == "elevenlabs":
            engine = ElevenLabsEngine(api_key=self._elevenlabs_api_key)
        else:
            raise ValueError(f"Unsupported TTS provider: {provider}")

        self._engines[provider] = engine
        return engine

    def get_default_voice_id(
        self,
        language: str = "ko",
        gender: str = "male",
    ) -> str:
        """Get default voice ID based on language and gender.

        Args:
            language: Language code ("ko", "en")
            gender: Voice gender ("male", "female")

        Returns:
            Default voice ID
        """
        if language.startswith("ko"):
            if gender == "male":
                return self._config.default_voice_ko_male
            return self._config.default_voice_ko_female
        else:
            return self._config.default_voice_en

    @property
    def available_providers(self) -> list[str]:
        """Get list of available TTS providers.

        Returns:
            List of provider names
        """
        return ["edge-tts", "elevenlabs"]


__all__ = ["TTSEngineFactory", "TTSProvider"]
