"""Tests for Calendar Club API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.index import app


@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_healthy(self, client: TestClient) -> None:
        """Test /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_returns_ok(self, client: TestClient) -> None:
        """Test / returns ok status."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestChatEndpoint:
    """Test simple chat endpoint."""

    def test_chat_without_api_key(self, client: TestClient) -> None:
        """Test /api/chat returns error without API key."""
        response = client.post(
            "/api/chat",
            json={"message": "Hello"},
        )
        # Should return 500 without OPENAI_API_KEY
        assert response.status_code == 500
