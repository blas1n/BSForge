"""HTTP Client for shared connection management.

This module provides a managed httpx.AsyncClient for reusing
HTTP connections across the application.
"""

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


class HTTPClient:
    """Managed HTTP client with connection reuse.

    Designed for DI injection. Create once at application startup,
    inject where needed, close at shutdown.

    Example:
        # In container setup
        http_client = HTTPClient()

        # In service
        response = await http_client.get("https://api.example.com")

        # At shutdown
        await http_client.close()
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_connections: int = 20,
        max_keepalive_connections: int = 10,
    ) -> None:
        """Initialize HTTP client.

        Args:
            timeout: Request timeout in seconds
            max_connections: Maximum number of connections
            max_keepalive_connections: Maximum keepalive connections
        """
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            ),
            follow_redirects=True,
        )
        logger.info(
            "HTTP client initialized",
            extra={
                "timeout": timeout,
                "max_connections": max_connections,
                "max_keepalive": max_keepalive_connections,
            },
        )

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Send GET request."""
        return await self._client.get(url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Send POST request."""
        return await self._client.post(url, **kwargs)

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        await self._client.aclose()
        logger.info("HTTP client closed")


__all__ = ["HTTPClient"]
