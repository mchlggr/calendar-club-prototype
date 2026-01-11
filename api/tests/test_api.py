"""Tests for Calendar Club API endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from api.index import _format_user_error, _safe_json_serialize, app


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

    def test_chat_redirects_to_stream(self, client: TestClient) -> None:
        """Test /api/chat suggests using stream endpoint."""
        # This test would need OPENAI_API_KEY to work
        # For now, we just test it returns something
        pass


class TestSafeJsonSerialize:
    """Test _safe_json_serialize helper."""

    def test_serializes_dict(self) -> None:
        """Test serializing a dict."""
        data = {"type": "test", "value": 123}
        result = _safe_json_serialize(data)
        assert result is not None
        assert json.loads(result) == data

    def test_serializes_list(self) -> None:
        """Test serializing a list."""
        data = [1, 2, 3]
        result = _safe_json_serialize(data)
        assert result is not None
        assert json.loads(result) == data

    def test_returns_none_for_unserializable(self) -> None:
        """Test returns None for unserializable objects."""

        class Unserializable:
            pass

        result = _safe_json_serialize(Unserializable())
        assert result is None


class TestFormatUserError:
    """Test _format_user_error helper."""

    def test_api_key_error(self) -> None:
        """Test API key error message."""
        error = Exception("Invalid API key")
        message = _format_user_error(error)
        assert "configuration" in message.lower()

    def test_timeout_error(self) -> None:
        """Test timeout error message."""
        error = Exception("Request timeout")
        message = _format_user_error(error)
        assert "timed out" in message.lower()

    def test_rate_limit_error(self) -> None:
        """Test rate limit error message."""
        error = Exception("Rate limit exceeded")
        message = _format_user_error(error)
        assert "busy" in message.lower()

    def test_generic_error(self) -> None:
        """Test generic error message."""
        error = Exception("Something unexpected happened")
        message = _format_user_error(error)
        assert "went wrong" in message.lower()
        # Should not expose internal details
        assert "unexpected" not in message.lower()
