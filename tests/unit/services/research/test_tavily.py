"""Unit tests for Tavily client."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.config.research import ResearchConfig
from app.services.research.tavily import TavilyClient


@pytest.fixture
def mock_http_client() -> MagicMock:
    """Create a mock HTTP client."""
    return MagicMock()


@pytest.fixture
def tavily_client(mock_http_client: MagicMock) -> TavilyClient:
    """Create a Tavily client for testing."""
    return TavilyClient(
        api_key="test-api-key",
        http_client=mock_http_client,
        config=ResearchConfig(
            search_depth="basic",
            topic_type="general",
            include_answer=True,
            timeout=30,
        ),
    )


@pytest.fixture
def mock_response_data() -> dict:
    """Create mock Tavily API response."""
    return {
        "query": "test query",
        "answer": "This is the AI answer.",
        "results": [
            {
                "title": "Test Result 1",
                "url": "https://example.com/1",
                "content": "Test content 1",
                "score": 0.95,
            },
            {
                "title": "Test Result 2",
                "url": "https://example.org/2",
                "content": "Test content 2",
                "score": 0.85,
            },
        ],
    }


@pytest.mark.asyncio
async def test_search_success(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
    mock_response_data: dict,
) -> None:
    """Test successful search returns correct results."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(return_value=mock_response)

    response = await tavily_client.search("test query", max_results=5)

    assert response.query == "test query"
    assert response.answer == "This is the AI answer."
    assert len(response.results) == 2
    assert response.results[0].title == "Test Result 1"
    assert response.results[0].url == "https://example.com/1"
    assert response.results[0].score == 0.95
    assert response.results[1].title == "Test Result 2"


@pytest.mark.asyncio
async def test_search_extracts_domain(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
    mock_response_data: dict,
) -> None:
    """Test that source domain is extracted from URL."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(return_value=mock_response)

    response = await tavily_client.search("test query")

    assert response.results[0].source == "example.com"
    assert response.results[1].source == "example.org"


@pytest.mark.asyncio
async def test_search_http_error_returns_empty(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
) -> None:
    """Test HTTP error returns empty results."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    error = httpx.HTTPStatusError(
        "Server Error",
        request=MagicMock(),
        response=mock_response,
    )

    mock_http_client.post = AsyncMock(side_effect=error)

    response = await tavily_client.search("test query")

    assert response.query == "test query"
    assert len(response.results) == 0
    assert response.answer is None


@pytest.mark.asyncio
async def test_search_request_error_returns_empty(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
) -> None:
    """Test request error returns empty results."""
    error = httpx.RequestError("Connection failed")

    mock_http_client.post = AsyncMock(side_effect=error)

    response = await tavily_client.search("test query")

    assert response.query == "test query"
    assert len(response.results) == 0


@pytest.mark.asyncio
async def test_search_batch(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
    mock_response_data: dict,
) -> None:
    """Test batch search runs queries in parallel."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_response_data
    mock_response.raise_for_status = MagicMock()

    mock_http_client.post = AsyncMock(return_value=mock_response)

    responses = await tavily_client.search_batch(
        ["query1", "query2", "query3"],
        max_results_per_query=3,
    )

    assert len(responses) == 3
    for response in responses:
        assert len(response.results) == 2


@pytest.mark.asyncio
async def test_health_check_success(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
) -> None:
    """Test health check returns True on success."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_http_client.post = AsyncMock(return_value=mock_response)

    result = await tavily_client.health_check()

    assert result is True


@pytest.mark.asyncio
async def test_health_check_failure(
    tavily_client: TavilyClient,
    mock_http_client: MagicMock,
) -> None:
    """Test health check returns False on failure."""
    mock_http_client.post = AsyncMock(side_effect=Exception("Connection failed"))

    result = await tavily_client.health_check()

    assert result is False


def test_extract_domain() -> None:
    """Test domain extraction from URLs."""
    assert TavilyClient._extract_domain("https://example.com/path") == "example.com"
    assert TavilyClient._extract_domain("https://sub.example.org/") == "sub.example.org"
    assert TavilyClient._extract_domain("invalid-url") == "invalid-url"
