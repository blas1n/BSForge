"""TTS (Text-to-Speech) engines.

This module provides TTS implementations:
- EdgeTTSEngine: Free Microsoft Edge TTS with word timestamps
- ElevenLabsEngine: High-quality ElevenLabs TTS (premium)
- TTSEngineFactory: Factory for creating TTS engines
"""

from app.services.generator.tts.base import BaseTTSEngine, TTSResult, WordTimestamp
from app.services.generator.tts.edge import EdgeTTSEngine
from app.services.generator.tts.factory import TTSEngineFactory

__all__ = [
    "BaseTTSEngine",
    "TTSResult",
    "WordTimestamp",
    "EdgeTTSEngine",
    "TTSEngineFactory",
]
