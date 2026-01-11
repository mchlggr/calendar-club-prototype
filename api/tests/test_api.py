"""Tests for Calendar Club API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.index import app


@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


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

    def test_chat_without_api_key(self, client: TestClient, monkeypatch) -> None:
        """Test /api/chat returns error without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        response = client.post(
            "/api/chat",
            json={"message": "Hello"},
        )
        # Should return 500 without OPENAI_API_KEY
        assert response.status_code == 500
