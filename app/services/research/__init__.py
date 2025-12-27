"""Web research service package.

This package provides web search capabilities for enriching topic content
with additional information from the web.
"""

from app.services.research.base import BaseResearchClient, ResearchResponse, ResearchResult
from app.services.research.query_builder import ResearchQueryBuilder
from app.services.research.tavily import TavilyClient

__all__ = [
    "BaseResearchClient",
    "ResearchResponse",
    "ResearchResult",
    "ResearchQueryBuilder",
    "TavilyClient",
]
