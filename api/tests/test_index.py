"""Tests for FastAPI endpoints."""

import os

import pytest
from fastapi.testclient import TestClient

from api.config import get_settings
from api.index import app


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_healthy(self, client):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_returns_ok(self, client):
        """Root endpoint should return ok status."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestChatStreamEndpoint:
    """Test chat streaming endpoint."""

    def test_missing_openai_key_returns_500(self, client, monkeypatch):
        """Without OPENAI_API_KEY, should return 500 error."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        _clear_settings_cache()
        response = client.post(
            "/api/chat/stream",
            json={"message": "hello"},
        )
        assert response.status_code == 500

    def test_valid_request_with_api_key(self, client):
        """Request with valid API key should be accepted."""
        # Skip if no API key - this is an integration test
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY required for this test")
        response = client.post(
            "/api/chat/stream",
            json={"message": "What's happening this weekend?"},
        )
        assert response.status_code == 200


class TestCalendarExport:
    """Test calendar export endpoints."""

    @pytest.mark.skip(reason="Calendar export endpoints not yet implemented")
    def test_export_single_event(self, client):
        """Export single event should return ICS file."""
        response = client.post(
            "/api/calendar/export",
            json={
                "title": "Test Event",
                "start": "2026-01-10T18:00:00",
                "end": "2026-01-10T20:00:00",
                "description": "Test description",
                "location": "Test Venue",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")
        assert "BEGIN:VCALENDAR" in response.content.decode()

    @pytest.mark.skip(reason="Calendar export endpoints not yet implemented")
    def test_export_multiple_events(self, client):
        """Export multiple events should return combined ICS file."""
        response = client.post(
            "/api/calendar/export-multiple",
            json={
                "events": [
                    {
                        "title": "Event 1",
                        "start": "2026-01-10T18:00:00",
                    },
                    {
                        "title": "Event 2",
                        "start": "2026-01-11T18:00:00",
                    },
                ]
            },
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert content.count("BEGIN:VEVENT") == 2

    @pytest.mark.skip(reason="Calendar export endpoints not yet implemented")
    def test_export_empty_events_fails(self, client):
        """Export with no events should return 400."""
        response = client.post(
            "/api/calendar/export-multiple",
            json={"events": []},
        )
        assert response.status_code == 400
