"""Tests for SearchAgent and tools."""

import os
from unittest.mock import patch

from api.agents.search import (
    EventResult,
    RefinementInput,
    SearchResult,
    _get_mock_events,
    refine_results,
    search_events,
)
from api.config import get_settings
from api.models import EventFeedback, Rating, SearchProfile


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


class TestEventResultModel:
    """Test EventResult Pydantic model validation."""

    def test_valid_event_result(self):
        """Test valid EventResult construction."""
        event = EventResult(
            id="evt-001",
            title="Test Event",
            date="2026-01-10T18:00:00",
            location="Test Venue",
            category="ai",
            description="Test description",
            is_free=True,
            distance_miles=2.5,
        )
        assert event.id == "evt-001"
        assert event.is_free is True

    def test_event_result_with_optional_fields(self):
        """Test EventResult with optional fields."""
        event = EventResult(
            id="evt-002",
            title="Paid Event",
            date="2026-01-10T18:00:00",
            location="Test Venue",
            category="startup",
            description="Test",
            is_free=False,
            price_amount=50,
            distance_miles=3.0,
            url="https://eventbrite.com/e/123",
        )
        assert event.price_amount == 50
        assert event.url == "https://eventbrite.com/e/123"


class TestSearchResult:
    """Test SearchResult model."""

    def test_search_result_with_events(self):
        """Test SearchResult with events."""
        events = _get_mock_events()
        result = SearchResult(
            events=events,
            source="demo",
            message="Demo mode active",
        )
        assert len(result.events) > 0
        assert result.source == "demo"

    def test_search_result_empty(self):
        """Test SearchResult with no events."""
        result = SearchResult(
            events=[],
            source="unavailable",
            message="No events found",
        )
        assert len(result.events) == 0
        assert result.source == "unavailable"


class TestSearchEventsFunction:
    """Test search_events tool function."""

    def test_demo_mode_returns_mock_events(self):
        """With DEMO_MODE=true, should return mock events with demo source."""
        with patch.dict(os.environ, {"DEMO_MODE": "true"}, clear=True):
            _clear_settings_cache()
            profile = SearchProfile(location="Columbus, OH")
            result = search_events(profile)

            assert result.source == "demo"
            assert len(result.events) > 0
            assert result.message

    def test_no_api_key_returns_unavailable(self):
        """Without API key and DEMO_MODE=false, should return unavailable."""
        with patch.dict(os.environ, {"DEMO_MODE": "false"}, clear=True):
            _clear_settings_cache()
            os.environ.pop("EVENTBRITE_API_KEY", None)

            profile = SearchProfile(location="Columbus, OH")
            result = search_events(profile)

            assert result.source == "unavailable"
            assert len(result.events) == 0
            assert result.message is not None


class TestRefineResults:
    """Test refine_results tool function."""

    def test_refine_with_feedback_demo_mode(self):
        """In demo mode, refinement returns sample events."""
        with patch.dict(os.environ, {"DEMO_MODE": "true"}, clear=True):
            _clear_settings_cache()
            feedback = [
                EventFeedback(event_id="evt-001", rating=Rating.YES),
                EventFeedback(event_id="evt-002", rating=Rating.NO, reason="too far"),
            ]
            input_data = RefinementInput(feedback=feedback)
            result = refine_results(input_data)

            assert result.source == "demo"
            assert "closer" in result.explanation.lower()
            assert result.events

    def test_refine_without_demo_mode(self):
        """Without demo mode, refinement is honest about limitations."""
        with patch.dict(os.environ, {"DEMO_MODE": "false"}, clear=True):
            _clear_settings_cache()
            feedback = [
                EventFeedback(
                    event_id="evt-001", rating=Rating.NO, reason="too expensive"
                ),
            ]
            input_data = RefinementInput(feedback=feedback)
            result = refine_results(input_data)

            assert result.source == "unavailable"
            assert len(result.events) == 0
            assert (
                "search" in result.explanation.lower()
                or "criteria" in result.explanation.lower()
            )


class TestMockEvents:
    """Test mock event data structure."""

    def test_mock_events_valid(self):
        """Mock events should be valid EventResult instances."""
        events = _get_mock_events()
        assert len(events) >= 3
        for event in events:
            assert isinstance(event, EventResult)
            assert event.id.startswith("evt-")

    def test_mock_events_have_required_fields(self):
        """Mock events should have all required fields."""
        events = _get_mock_events()
        for event in events:
            assert event.title
            assert event.date
            assert event.location
            assert event.category
