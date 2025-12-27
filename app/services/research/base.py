"""Base classes for research providers.

This module defines the abstract interface for web research providers
and common data structures.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ResearchResult:
    """Result from web research.

    Attributes:
        title: Title of the source
        url: URL of the source
        content: Extracted or summarized content
        score: Relevance score (0-1)
        source: Source name (e.g., website domain)
        raw_content: Full raw content if available
    """

    title: str
    url: str
    content: str
    score: float
    source: str
    raw_content: str | None = None


@dataclass
class ResearchResponse:
    """Complete response from research query.

    Attributes:
        query: Original search query
        results: List of research results
        answer: AI-generated answer summarizing results (if available)
        response_time: Response time in seconds
    """

    query: str
    results: list[ResearchResult] = field(default_factory=list)
    answer: str | None = None
    response_time: float = 0.0


class BaseResearchClient(ABC):
    """Abstract base class for research providers.

    All research providers must implement this interface.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> ResearchResponse:
        """Search the web for information.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            ResearchResponse with results and optional AI answer
        """
        ...

    async def search_batch(
        self,
        queries: list[str],
        max_results_per_query: int = 5,
    ) -> list[ResearchResponse]:
        """Search multiple queries in batch.

        Default implementation runs queries sequentially.
        Subclasses can override for parallel execution.

        Args:
            queries: List of search queries
            max_results_per_query: Maximum results per query

        Returns:
            List of ResearchResponse, one per query
        """
        results = []
        for query in queries:
            response = await self.search(query, max_results_per_query)
            results.append(response)
        return results

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the research provider is available.

        Returns:
            True if provider is healthy
        """
        ...


__all__ = [
    "ResearchResult",
    "ResearchResponse",
    "BaseResearchClient",
]
