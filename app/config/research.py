"""Research service configuration models.

This module provides typed Pydantic configuration for web research:
- Tavily API integration
- Query strategy selection
- Search parameters
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QueryStrategy(str, Enum):
    """Strategy for generating research queries from topic/cluster.

    Attributes:
        KEYWORD: Build queries from combined_terms keywords
        TITLE: Use topic title directly for search
        LLM: Generate optimal queries using LLM
    """

    KEYWORD = "keyword"
    TITLE = "title"
    LLM = "llm"


class ResearchConfig(BaseModel):
    """Web research configuration.

    Attributes:
        enabled: Whether web research is enabled
        provider: Research provider (currently only tavily supported)
        query_strategy: Strategy for generating search queries
        search_depth: Tavily search depth (basic or advanced)
        topic_type: Tavily topic type (general or news)
        max_queries: Maximum number of search queries to run
        max_results_per_query: Maximum results per query
        include_answer: Include Tavily's AI-generated answer
        timeout: Request timeout in seconds
    """

    enabled: bool = Field(default=True, description="Enable web research")
    provider: Literal["tavily"] = Field(default="tavily", description="Research provider")
    query_strategy: QueryStrategy = Field(
        default=QueryStrategy.KEYWORD,
        description="Strategy for generating search queries",
    )
    search_depth: Literal["basic", "advanced"] = Field(
        default="basic",
        description="Search depth (advanced for more thorough results)",
    )
    topic_type: Literal["general", "news"] = Field(
        default="general",
        description="Topic type (news for time-sensitive content)",
    )
    max_queries: int = Field(default=3, ge=1, le=10, description="Max search queries")
    max_results_per_query: int = Field(default=5, ge=1, le=10, description="Results per query")
    include_answer: bool = Field(default=True, description="Include AI-generated answer")
    timeout: float = Field(default=30.0, ge=5.0, le=120.0, description="Request timeout")


__all__ = [
    "QueryStrategy",
    "ResearchConfig",
]
