"""Tests for SearchAgent and tools."""

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from api.agents.search import (
    EventResult,
    RefinementInput,
    SearchResult,
    _fetch_cached_events,
    refine_results,
    search_events,
)
from api.config import get_settings
from api.models import EventFeedback, Rating, SearchProfile
from api.services.event_cache import CachedEvent, EventCacheService


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

    @pytest.mark.asyncio
    async def test_no_api_key_returns_unavailable(self):
        """Without API key, should return unavailable."""
        with patch.dict(os.environ, {}, clear=True):
            _clear_settings_cache()
            os.environ.pop("EVENTBRITE_API_KEY", None)

            profile = SearchProfile()
            result = await search_events(profile)

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


@pytest.mark.skip(reason="Tests need update for slit EventCache interface")
class TestMultiSourceSearch:
    """Tests for multi-source search integration."""

    @pytest.fixture
    def temp_cache(self):
        """Create a temporary cache for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            cache = EventCacheService(db_path=Path(f.name), ttl_hours=24)
            yield cache

    def test_fetch_cached_events_empty_cache(self, temp_cache):
        """Test fetching from empty cache returns empty list."""
        with patch("api.agents.search.get_event_cache", return_value=temp_cache):
            profile = SearchProfile()
            events = _fetch_cached_events(profile, sources=["luma"])
            assert events == []

    def test_fetch_cached_events_returns_luma_events(self, temp_cache):
        """Test fetching Luma events from cache."""
        # Add some Luma events to cache
        luma_event = CachedEvent(
            id="luma:test1",
            source="luma",
            external_id="test1",
            title="Luma Tech Meetup",
            start_time=datetime.now(UTC) + timedelta(days=1),
            location="Columbus, OH",
        )
        temp_cache.upsert(luma_event)

        with patch("api.agents.search.get_event_cache", return_value=temp_cache):
            profile = SearchProfile()
            events = _fetch_cached_events(profile, sources=["luma"])

            assert len(events) == 1
            assert events[0].title == "Luma Tech Meetup"
            assert events[0].id == "luma:test1"

    def test_fetch_cached_events_respects_free_only(self, temp_cache):
        """Test that free_only filter works on cached events."""
        # Add free and paid events
        temp_cache.upsert(
            CachedEvent(
                id="luma:free",
                source="luma",
                external_id="free",
                title="Free Event",
                is_free=True,
            )
        )
        temp_cache.upsert(
            CachedEvent(
                id="luma:paid",
                source="luma",
                external_id="paid",
                title="Paid Event",
                is_free=False,
                price_amount=50,
            )
        )

        with patch("api.agents.search.get_event_cache", return_value=temp_cache):
            profile = SearchProfile(free_only=True)
            events = _fetch_cached_events(profile, sources=["luma"])

            assert len(events) == 1
            assert events[0].title == "Free Event"

    @pytest.mark.asyncio
    async def test_search_events_merges_sources(self, temp_cache):
        """Test that search_events merges cache with Eventbrite."""
        # Add Luma event to cache
        luma_event = CachedEvent(
            id="luma:merge1",
            source="luma",
            external_id="merge1",
            title="Luma Event for Merge",
            start_time=datetime.now(UTC) + timedelta(days=1),
        )
        temp_cache.upsert(luma_event)

        with (
            patch("api.agents.search.get_event_cache", return_value=temp_cache),
            patch.dict(os.environ, {"EVENTBRITE_API_KEY": ""}, clear=False),
        ):
            _clear_settings_cache()
            profile = SearchProfile()
            result = await search_events(profile)

            # Should have Luma events even without Eventbrite key
            assert len(result.events) >= 1
            assert result.source == "luma"

    @pytest.mark.asyncio
    async def test_search_events_deduplicates_by_title(self, temp_cache):
        """Test that duplicate titles are removed."""
        # Add duplicate events
        temp_cache.upsert(
            CachedEvent(
                id="luma:dup1",
                source="luma",
                external_id="dup1",
                title="Duplicate Event",
                start_time=datetime.now(UTC) + timedelta(days=1),
            )
        )
        temp_cache.upsert(
            CachedEvent(
                id="luma:dup2",
                source="luma",
                external_id="dup2",
                title="duplicate event",  # Same title, different case
                start_time=datetime.now(UTC) + timedelta(days=2),
            )
        )

        with (
            patch("api.agents.search.get_event_cache", return_value=temp_cache),
            patch.dict(os.environ, {"EVENTBRITE_API_KEY": ""}, clear=False),
        ):
            _clear_settings_cache()
            profile = SearchProfile()
            result = await search_events(profile)

            # Should be deduplicated
            assert len(result.events) == 1

    def test_search_result_multi_source_attribution(self):
        """Test that multi-source results have combined attribution."""
        result = SearchResult(
            events=[],
            source="luma+eventbrite",
            message=None,
        )
        assert "+" in result.source
        assert "luma" in result.source
        assert "eventbrite" in result.source
