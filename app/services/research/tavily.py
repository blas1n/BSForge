"""Tavily API client for web research.

Tavily provides AI-powered web search with content extraction
and optional AI-generated answers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from app.config.research import ResearchConfig
from app.services.research.base import BaseResearchClient, ResearchResponse, ResearchResult

if TYPE_CHECKING:
    from app.infrastructure.http_client import HTTPClient

logger = logging.getLogger(__name__)


class TavilyClient(BaseResearchClient):
    """Tavily web search API client.

    Provides async web search with AI-powered content extraction.

    Attributes:
        api_key: Tavily API key
        http_client: Shared HTTP client from DI
        config: Research configuration
    """

    BASE_URL = "https://api.tavily.com"

    def __init__(
        self,
        api_key: str,
        http_client: HTTPClient,
        config: ResearchConfig | None = None,
    ) -> None:
        """Initialize Tavily client.

        Args:
            api_key: Tavily API key
            http_client: Shared HTTP client from DI
            config: Optional research configuration
        """
        self.api_key = api_key
        self.http_client = http_client
        self.config = config or ResearchConfig()

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> ResearchResponse:
        """Search the web using Tavily API.

        Args:
            query: Search query string
            max_results: Maximum number of results

        Returns:
            ResearchResponse with results and optional AI answer
        """
        start_time = time.time()

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": self.config.search_depth,
            "topic": self.config.topic_type,
            "max_results": max_results,
            "include_answer": self.config.include_answer,
            "include_raw_content": False,
        }

        try:
            response = await self.http_client.post(
                f"{self.BASE_URL}/search",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            results = [
                ResearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                    source=self._extract_domain(item.get("url", "")),
                    raw_content=item.get("raw_content"),
                )
                for item in data.get("results", [])
            ]

            return ResearchResponse(
                query=query,
                results=results,
                answer=data.get("answer"),
                response_time=time.time() - start_time,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily API error: {e.response.status_code} - {e.response.text}")
            return ResearchResponse(
                query=query,
                results=[],
                response_time=time.time() - start_time,
            )
        except httpx.RequestError as e:
            logger.error(f"Tavily request error: {e}")
            return ResearchResponse(
                query=query,
                results=[],
                response_time=time.time() - start_time,
            )

    async def search_batch(
        self,
        queries: list[str],
        max_results_per_query: int = 5,
    ) -> list[ResearchResponse]:
        """Search multiple queries in parallel.

        Args:
            queries: List of search queries
            max_results_per_query: Maximum results per query

        Returns:
            List of ResearchResponse, one per query
        """
        tasks = [self.search(query, max_results_per_query) for query in queries]
        return await asyncio.gather(*tasks)

    async def search_images(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[str]:
        """Search for images using Tavily API.

        Args:
            query: Search query string (e.g., "BTS Jungkook")
            max_results: Maximum number of image URLs to return

        Returns:
            List of image URLs
        """
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "include_images": True,
            "include_answer": False,
            "include_raw_content": False,
            "max_results": 5,  # Text results (minimal)
        }

        try:
            response = await self.http_client.post(
                f"{self.BASE_URL}/search",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            images: list[str] = data.get("images", [])
            logger.info(f"Tavily image search for '{query}': found {len(images)} images")
            return images[:max_results]

        except httpx.HTTPStatusError as e:
            logger.error(f"Tavily image search error: {e.response.status_code}")
            return []
        except httpx.RequestError as e:
            logger.error(f"Tavily image search request error: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if Tavily API is available.

        Returns:
            True if API is accessible
        """
        try:
            response = await self.http_client.post(
                f"{self.BASE_URL}/search",
                json={
                    "api_key": self.api_key,
                    "query": "test",
                    "max_results": 1,
                },
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Tavily health check failed: {e}")
            return False

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain name
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc or url
        except Exception:
            return url


__all__ = ["TavilyClient"]
