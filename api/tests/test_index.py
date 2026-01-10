"""Tests for FastAPI endpoints."""

import os
from unittest.mock import Mock, patch

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

    def test_missing_openai_key_returns_error(self, client):
        """Without OPENAI_API_KEY, should return error event."""
        with patch.dict(os.environ, {}, clear=True):
            _clear_settings_cache()
            response = client.post(
                "/api/chat/stream",
                json={"session_id": "test-123", "message": "hello"},
            )
            assert response.status_code == 200
            content = response.content.decode()
            assert "error" in content.lower()

    def test_valid_request_format(self, client):
        """Request with valid format should be accepted."""
        async def _empty_stream():
            if False:
                yield None

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True):
            _clear_settings_cache()
            with patch("api.index.Runner") as mock_runner:
                mock_result = Mock()
                mock_result.stream_events = _empty_stream
                mock_runner.run_streamed.return_value = mock_result

                response = client.post(
                    "/api/chat/stream",
                    json={
                        "session_id": "test-session-123",
                        "message": "What's happening this weekend?",
                    },
                )
                assert response.status_code == 200


class TestCalendarExport:
    """Test calendar export endpoints."""

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

    def test_export_empty_events_fails(self, client):
        """Export with no events should return 400."""
        response = client.post(
            "/api/calendar/export-multiple",
            json={"events": []},
        )
        assert response.status_code == 400
