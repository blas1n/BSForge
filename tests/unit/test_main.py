"""Tests for app.main module."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client.

    Returns:
        FastAPI test client
    """
    return TestClient(app)


@pytest.mark.unit
def test_health_check(client: TestClient) -> None:
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "BSForge"
    assert "env" in data


@pytest.mark.unit
def test_root_endpoint(client: TestClient) -> None:
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "BSForge API"
    assert data["version"] == "0.1.0"
    assert "docs" in data


@pytest.mark.unit
def test_docs_available_in_development(client: TestClient) -> None:
    """Test that API docs are available."""
    # Docs should be available in development
    response = client.get("/docs")
    assert response.status_code == 200


@pytest.mark.unit
def test_cors_headers(client: TestClient) -> None:
    """Test CORS headers are present."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS middleware should add appropriate headers
    assert "access-control-allow-origin" in response.headers
