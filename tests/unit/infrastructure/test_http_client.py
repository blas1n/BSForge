"""Unit tests for HTTP client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.infrastructure.http_client import HTTPClient


class TestHTTPClientInit:
    """Tests for HTTPClient initialization."""

    @patch("app.infrastructure.http_client.httpx.AsyncClient")
    def test_init_default_values(self, mock_async_client):
        """Test initialization with default values."""
        HTTPClient()

        mock_async_client.assert_called_once()
        call_kwargs = mock_async_client.call_args[1]
        assert call_kwargs["follow_redirects"] is True

    @patch("app.infrastructure.http_client.httpx.AsyncClient")
    def test_init_custom_timeout(self, mock_async_client):
        """Test initialization with custom timeout."""
        HTTPClient(timeout=60.0)

        mock_async_client.assert_called_once()

    @patch("app.infrastructure.http_client.httpx.AsyncClient")
    def test_init_custom_connections(self, mock_async_client):
        """Test initialization with custom connection limits."""
        HTTPClient(
            max_connections=50,
            max_keepalive_connections=25,
        )

        mock_async_client.assert_called_once()


class TestHTTPClientRequests:
    """Tests for HTTPClient request methods."""

    @pytest.fixture
    def mock_client(self):
        """Create HTTPClient with mocked internal client."""
        with patch("app.infrastructure.http_client.httpx.AsyncClient") as mock:
            mock_instance = MagicMock()
            mock_instance.get = AsyncMock()
            mock_instance.post = AsyncMock()
            mock_instance.aclose = AsyncMock()
            mock.return_value = mock_instance

            client = HTTPClient()
            yield client, mock_instance

    @pytest.mark.asyncio
    async def test_get_request(self, mock_client):
        """Test GET request."""
        client, mock_instance = mock_client
        mock_instance.get.return_value = MagicMock(status_code=200)

        await client.get("https://example.com")

        mock_instance.get.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_get_with_params(self, mock_client):
        """Test GET request with query parameters."""
        client, mock_instance = mock_client

        await client.get("https://example.com", params={"key": "value"})

        mock_instance.get.assert_called_once_with("https://example.com", params={"key": "value"})

    @pytest.mark.asyncio
    async def test_get_with_headers(self, mock_client):
        """Test GET request with custom headers."""
        client, mock_instance = mock_client

        await client.get(
            "https://example.com",
            headers={"Authorization": "Bearer token"},
        )

        mock_instance.get.assert_called_once_with(
            "https://example.com",
            headers={"Authorization": "Bearer token"},
        )

    @pytest.mark.asyncio
    async def test_post_request(self, mock_client):
        """Test POST request."""
        client, mock_instance = mock_client
        mock_instance.post.return_value = MagicMock(status_code=201)

        await client.post("https://example.com/api")

        mock_instance.post.assert_called_once_with("https://example.com/api")

    @pytest.mark.asyncio
    async def test_post_with_json(self, mock_client):
        """Test POST request with JSON body."""
        client, mock_instance = mock_client

        await client.post(
            "https://example.com/api",
            json={"data": "value"},
        )

        mock_instance.post.assert_called_once_with(
            "https://example.com/api",
            json={"data": "value"},
        )

    @pytest.mark.asyncio
    async def test_post_with_data(self, mock_client):
        """Test POST request with form data."""
        client, mock_instance = mock_client

        await client.post(
            "https://example.com/api",
            data={"field": "value"},
        )

        mock_instance.post.assert_called_once_with(
            "https://example.com/api",
            data={"field": "value"},
        )


class TestHTTPClientClose:
    """Tests for HTTPClient close method."""

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing the client."""
        with patch("app.infrastructure.http_client.httpx.AsyncClient") as mock:
            mock_instance = MagicMock()
            mock_instance.aclose = AsyncMock()
            mock.return_value = mock_instance

            client = HTTPClient()
            await client.close()

            mock_instance.aclose.assert_called_once()
