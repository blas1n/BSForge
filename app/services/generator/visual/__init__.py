"""Visual sourcing services.

This module provides visual asset sourcing for video generation:
- PexelsClient: Stock video/image search and download
- PixabayClient: Additional stock video/image source (no attribution required)
- DALLEGenerator: DALL-E 3 image generation
- StableDiffusionGenerator: Local SD image generation via HTTP API
- FallbackGenerator: Solid color and gradient backgrounds
- VisualSourcingManager: Orchestrates visual sourcing with priority
"""

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)
from app.services.generator.visual.dall_e import DALLEGenerator
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.pixabay import PixabayClient
from app.services.generator.visual.stable_diffusion import StableDiffusionGenerator

__all__ = [
    "BaseVisualSource",
    "VisualAsset",
    "VisualSourceType",
    "PexelsClient",
    "PixabayClient",
    "DALLEGenerator",
    "StableDiffusionGenerator",
    "FallbackGenerator",
    "VisualSourcingManager",
]
