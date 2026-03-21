"""Visual sourcing services.

This module provides visual asset sourcing for video generation:
- PexelsClient: Stock video/image search and download
- WanVideoSource: Wan 2.2 T2V video generation via HTTP API
- VisualSourcingManager: Orchestrates visual sourcing with priority
"""

from app.services.generator.visual.base import (
    BaseVisualSource,
    VisualAsset,
    VisualSourceType,
)
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.pexels import PexelsClient
from app.services.generator.visual.wan_video_source import WanVideoSource

__all__ = [
    "BaseVisualSource",
    "VisualAsset",
    "VisualSourceType",
    "PexelsClient",
    "WanVideoSource",
    "VisualSourcingManager",
]
