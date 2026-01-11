"""Tests for SearchAgent and tools."""

import os
from unittest.mock import patch

from api.agents.search import (
    EventResult,
    RefinementInput,
    SearchResult,
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
        events = [
            EventResult(
                id="evt-001",
                title="Real Event",
                date="2026-01-10T18:00:00",
                location="Real Venue",
                category="ai",
                description="A real event",
                is_free=True,
                distance_miles=2.5,
            )
        ]
        result = SearchResult(
            events=events,
            source="eventbrite",
            message=None,
        )
        assert len(result.events) == 1
        assert result.source == "eventbrite"

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

    def test_no_api_key_returns_unavailable(self):
        """Without API key, should return unavailable."""
        with patch.dict(os.environ, {}, clear=True):
            _clear_settings_cache()
            os.environ.pop("EVENTBRITE_API_KEY", None)

            profile = SearchProfile()
            result = search_events(profile)

            assert result.source == "unavailable"
            assert len(result.events) == 0
            assert result.message is not None


class TestRefineResults:
    """Test refine_results tool function."""

    def test_refine_returns_unavailable(self):
        """Refinement returns unavailable since no real-time refinement yet."""
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

    def test_refine_includes_feedback_explanation(self):
        """Refinement should explain what it learned from feedback."""
        _clear_settings_cache()
        feedback = [
            EventFeedback(event_id="evt-001", rating=Rating.YES),
            EventFeedback(event_id="evt-002", rating=Rating.NO, reason="too far"),
        ]
        input_data = RefinementInput(feedback=feedback)
        result = refine_results(input_data)

        assert "closer" in result.explanation.lower()
