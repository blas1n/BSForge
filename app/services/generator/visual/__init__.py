"""Visual sourcing services.

This module provides visual asset sourcing for video generation:
- PexelsClient: Stock video/image search and download
- AIImageGenerator: DALL-E 3 image generation
- FallbackGenerator: Solid color and gradient backgrounds
- VisualSourcingManager: Orchestrates visual sourcing with priority
"""

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)
from app.services.generator.visual.fallback import FallbackGenerator
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.pexels import PexelsClient

__all__ = [
    "BaseVisualSource",
    "VisualAsset",
    "VisualSourceType",
    "PexelsClient",
    "FallbackGenerator",
    "VisualSourcingManager",
]
