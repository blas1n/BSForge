"""Shared fixtures for source collector tests."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.http_client import HTTPClient


@pytest.fixture
def source_id() -> uuid.UUID:
    """Create a test source UUID."""
    return uuid.uuid4()


@pytest.fixture
def mock_http_client() -> HTTPClient:
    """Create a mock HTTP client."""
    client = MagicMock(spec=HTTPClient)
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


def create_mock_response(json_data=None, text_data=None, status_code=200):
    """Create a mock HTTP response.

    Args:
        json_data: Data to return from json()
        text_data: Data to return from text property
        status_code: HTTP status code

    Returns:
        Mock response object
    """
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()

    if json_data is not None:
        response.json.return_value = json_data

    if text_data is not None:
        response.text = text_data

    return response
