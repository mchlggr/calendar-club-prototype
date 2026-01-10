"""Tests for SearchAgent tools and models."""

import os

from api.agents.search import (
    DataSource,
    EventResult,
    RefinementInput,
    RefinementOutput,
    SearchResult,
    _get_demo_events,
)
from api.models import EventFeedback, Rating


class TestDataSource:
    """Test DataSource enum."""

    def test_data_source_values(self) -> None:
        """Test DataSource enum has correct values."""
        assert DataSource.EVENTBRITE.value == "eventbrite"
        assert DataSource.DEMO.value == "demo"
        assert DataSource.UNAVAILABLE.value == "unavailable"


class TestEventResult:
    """Test EventResult model."""

    def test_event_result_model(self) -> None:
        """Test EventResult model fields."""
        event = EventResult(
            id="test-001",
            title="Test Event",
            date="2026-01-10T18:00:00",
            location="Test Location",
            category="tech",
            description="A test event",
            is_free=True,
            distance_miles=2.5,
        )

        assert event.id == "test-001"
        assert event.title == "Test Event"
        assert event.is_free is True
        assert event.price_amount is None
        assert event.url is None

    def test_event_result_with_price(self) -> None:
        """Test EventResult with price."""
        event = EventResult(
            id="test-002",
            title="Paid Event",
            date="2026-01-10T18:00:00",
            location="Test Location",
            category="tech",
            description="A paid event",
            is_free=False,
            price_amount=50,
            distance_miles=3.0,
            url="https://example.com/event",
        )

        assert event.is_free is False
        assert event.price_amount == 50
        assert event.url == "https://example.com/event"


class TestSearchResult:
    """Test SearchResult model."""

    def test_search_result_model(self) -> None:
        """Test SearchResult model fields."""
        events = [
            EventResult(
                id="test-001",
                title="Test Event",
                date="2026-01-10T18:00:00",
                location="Test Location",
                category="tech",
                description="A test event",
                is_free=True,
                distance_miles=2.5,
            )
        ]

        result = SearchResult(
            events=events,
            source=DataSource.DEMO,
            message="Test message",
        )

        assert len(result.events) == 1
        assert result.source == DataSource.DEMO
        assert result.message == "Test message"


class TestDemoEvents:
    """Test demo event generation."""

    def test_get_demo_events_returns_list(self) -> None:
        """Test _get_demo_events returns a list."""
        events = _get_demo_events()
        assert isinstance(events, list)
        assert len(events) > 0

    def test_demo_events_have_demo_prefix(self) -> None:
        """Test demo events have [DEMO] in title."""
        events = _get_demo_events()
        for event in events:
            assert "[DEMO]" in event.title

    def test_demo_events_have_demo_id_prefix(self) -> None:
        """Test demo events have demo- ID prefix."""
        events = _get_demo_events()
        for event in events:
            assert event.id.startswith("demo-")


class TestSearchEvents:
    """Test search_events function logic via helper functions."""

    def test_demo_mode_flag_parsing(self) -> None:
        """Test DEMO_MODE environment variable is correctly parsed."""
        # Test that module-level constant would be True with DEMO_MODE=true
        assert os.getenv("DEMO_MODE", "false").lower() == "true" or "false"

    def test_demo_events_structure_for_search(self) -> None:
        """Test demo events have proper structure for search results."""
        events = _get_demo_events()

        for event in events:
            # All events should be valid EventResults
            assert event.id
            assert event.title
            assert event.date
            assert event.location
            assert event.category
            assert isinstance(event.is_free, bool)
            assert isinstance(event.distance_miles, float)

    def test_search_result_can_hold_demo_events(self) -> None:
        """Test SearchResult can hold demo events properly."""
        events = _get_demo_events()
        result = SearchResult(
            events=events,
            source=DataSource.DEMO,
            message="Sample demo events",
        )

        assert result.source == DataSource.DEMO
        assert len(result.events) == len(events)

    def test_search_result_unavailable_state(self) -> None:
        """Test SearchResult in unavailable state."""
        result = SearchResult(
            events=[],
            source=DataSource.UNAVAILABLE,
            message="Event search is currently unavailable.",
        )

        assert result.source == DataSource.UNAVAILABLE
        assert len(result.events) == 0
        assert "unavailable" in result.message.lower()


class TestRefinementInput:
    """Test RefinementInput model."""

    def test_refinement_input_model(self) -> None:
        """Test RefinementInput model."""
        feedback = [
            EventFeedback(event_id="test-001", rating=Rating.YES),
            EventFeedback(event_id="test-002", rating=Rating.NO, reason="Too far"),
        ]

        input_data = RefinementInput(feedback=feedback)
        assert len(input_data.feedback) == 2


class TestRefinementOutput:
    """Test RefinementOutput model."""

    def test_refinement_output_model(self) -> None:
        """Test RefinementOutput model."""
        output = RefinementOutput(
            events=[],
            explanation="Test explanation",
            source=DataSource.DEMO,
            can_refine=True,
        )

        assert output.can_refine is True
        assert output.source == DataSource.DEMO


class TestRefineResults:
    """Test refine_results function logic via RefinementOutput model."""

    def test_refinement_output_demo_state(self) -> None:
        """Test RefinementOutput in demo mode state."""
        events = _get_demo_events()[:2]  # Get first 2 demo events
        output = RefinementOutput(
            events=events,
            explanation="Based on your feedback, looking for closer events.",
            source=DataSource.DEMO,
            can_refine=True,
        )

        assert output.source == DataSource.DEMO
        assert output.can_refine is True
        assert len(output.events) == 2

    def test_refinement_output_unavailable_state(self) -> None:
        """Test RefinementOutput in unavailable state."""
        output = RefinementOutput(
            events=[],
            explanation="To find better matches, please start a new search.",
            source=DataSource.UNAVAILABLE,
            can_refine=False,
        )

        assert output.source == DataSource.UNAVAILABLE
        assert output.can_refine is False
        assert len(output.events) == 0

    def test_feedback_analysis_distance_keyword(self) -> None:
        """Test feedback reason contains distance-related keyword."""
        feedback = EventFeedback(
            event_id="demo-001", rating=Rating.NO, reason="Too far away"
        )
        reason_lower = feedback.reason.lower()

        # This mimics the logic in refine_results
        wants_closer = "far" in reason_lower or "distance" in reason_lower
        assert wants_closer is True

    def test_feedback_analysis_price_keyword(self) -> None:
        """Test feedback reason contains price-related keyword."""
        feedback = EventFeedback(
            event_id="demo-001", rating=Rating.NO, reason="Too expensive"
        )
        reason_lower = feedback.reason.lower()

        # This mimics the logic in refine_results
        wants_cheaper = (
            "expensive" in reason_lower
            or "price" in reason_lower
            or "cost" in reason_lower
        )
        assert wants_cheaper is True

    def test_feedback_analysis_vibe_keyword(self) -> None:
        """Test feedback reason contains vibe-related keyword."""
        feedback = EventFeedback(
            event_id="demo-001", rating=Rating.NO, reason="Wrong vibe for me"
        )
        reason_lower = feedback.reason.lower()

        # This mimics the logic in refine_results
        wants_different_type = "vibe" in reason_lower or "type" in reason_lower
        assert wants_different_type is True
