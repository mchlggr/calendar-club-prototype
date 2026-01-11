"""Tests for the event cache service."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from api.services.event_cache import CachedEvent, EventCacheService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def cache(temp_db):
    """Create a cache service with a temporary database."""
    return EventCacheService(db_path=temp_db, ttl_hours=24)


class TestCachedEventModel:
    """Tests for CachedEvent model."""

    def test_create_cached_event(self):
        """Test creating a cached event with required fields."""
        event = CachedEvent(
            id="luma:test123",
            source="luma",
            external_id="test123",
            title="Test Event",
        )
        assert event.id == "luma:test123"
        assert event.source == "luma"
        assert event.external_id == "test123"
        assert event.title == "Test Event"
        assert event.is_free is True  # Default
        assert event.category == "community"  # Default

    def test_create_cached_event_with_all_fields(self):
        """Test creating a cached event with all optional fields."""
        now = datetime.now(UTC)
        event = CachedEvent(
            id="eventbrite:456",
            source="eventbrite",
            external_id="456",
            title="Full Event",
            description="A complete event description",
            start_time=now,
            end_time=now + timedelta(hours=2),
            location="123 Main St, Columbus, OH",
            url="https://eventbrite.com/e/456",
            category="tech",
            is_free=False,
            price_amount=25,
            host_name="Tech Meetup",
            cover_image_url="https://example.com/image.jpg",
            raw_data={"original": "data"},
        )
        assert event.description == "A complete event description"
        assert event.is_free is False
        assert event.price_amount == 25


class TestEventCacheService:
    """Tests for EventCacheService."""

    def test_upsert_and_get_by_source(self, cache):
        """Test inserting and retrieving events by source."""
        event = CachedEvent(
            id="luma:abc",
            source="luma",
            external_id="abc",
            title="Luma Event",
            start_time=datetime.now(UTC),
        )
        cache.upsert(event)

        events = cache.get_by_source("luma")
        assert len(events) == 1
        assert events[0].title == "Luma Event"

    def test_upsert_updates_existing(self, cache):
        """Test that upsert updates existing events."""
        event1 = CachedEvent(
            id="luma:abc",
            source="luma",
            external_id="abc",
            title="Original Title",
        )
        cache.upsert(event1)

        event2 = CachedEvent(
            id="luma:abc",
            source="luma",
            external_id="abc",
            title="Updated Title",
        )
        cache.upsert(event2)

        events = cache.get_by_source("luma")
        assert len(events) == 1
        assert events[0].title == "Updated Title"

    def test_upsert_many(self, cache):
        """Test bulk inserting events."""
        events = [
            CachedEvent(
                id=f"luma:{i}",
                source="luma",
                external_id=str(i),
                title=f"Event {i}",
            )
            for i in range(5)
        ]
        count = cache.upsert_many(events)
        assert count == 5
        assert cache.count("luma") == 5

    def test_search_by_date_range(self, cache):
        """Test searching events by date range."""
        now = datetime.now(UTC)

        # Event in the past
        past_event = CachedEvent(
            id="luma:past",
            source="luma",
            external_id="past",
            title="Past Event",
            start_time=now - timedelta(days=7),
        )
        cache.upsert(past_event)

        # Event in the future
        future_event = CachedEvent(
            id="luma:future",
            source="luma",
            external_id="future",
            title="Future Event",
            start_time=now + timedelta(days=7),
        )
        cache.upsert(future_event)

        # Search for future events only
        results = cache.search(start_after=now)
        assert len(results) == 1
        assert results[0].title == "Future Event"

    def test_search_by_sources(self, cache):
        """Test filtering search by multiple sources."""
        cache.upsert(
            CachedEvent(
                id="luma:1",
                source="luma",
                external_id="1",
                title="Luma Event",
            )
        )
        cache.upsert(
            CachedEvent(
                id="eventbrite:1",
                source="eventbrite",
                external_id="1",
                title="Eventbrite Event",
            )
        )
        cache.upsert(
            CachedEvent(
                id="other:1",
                source="other",
                external_id="1",
                title="Other Event",
            )
        )

        results = cache.search(sources=["luma", "eventbrite"])
        assert len(results) == 2
        titles = {e.title for e in results}
        assert "Luma Event" in titles
        assert "Eventbrite Event" in titles

    def test_search_by_location(self, cache):
        """Test searching events by location substring."""
        cache.upsert(
            CachedEvent(
                id="luma:columbus",
                source="luma",
                external_id="columbus",
                title="Columbus Event",
                location="123 High St, Columbus, OH",
            )
        )
        cache.upsert(
            CachedEvent(
                id="luma:nyc",
                source="luma",
                external_id="nyc",
                title="NYC Event",
                location="456 Broadway, New York, NY",
            )
        )

        results = cache.search(location_contains="columbus")
        assert len(results) == 1
        assert results[0].title == "Columbus Event"

    def test_expired_events_excluded_by_default(self, cache):
        """Test that expired events are excluded from searches."""
        # Create event with expired TTL
        expired_event = CachedEvent(
            id="luma:expired",
            source="luma",
            external_id="expired",
            title="Expired Event",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        cache.upsert(expired_event)

        # Should not appear in normal search
        results = cache.search()
        assert len(results) == 0

        # Should appear with include_expired=True
        results = cache.search(include_expired=True)
        assert len(results) == 1

    def test_delete_expired(self, cache):
        """Test deleting expired events."""
        # Add expired event
        expired_event = CachedEvent(
            id="luma:expired",
            source="luma",
            external_id="expired",
            title="Expired Event",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        cache.upsert(expired_event)

        # Add valid event
        valid_event = CachedEvent(
            id="luma:valid",
            source="luma",
            external_id="valid",
            title="Valid Event",
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        cache.upsert(valid_event)

        deleted = cache.delete_expired()
        assert deleted == 1
        assert cache.count() == 1

    def test_clear_all(self, cache):
        """Test clearing all events."""
        for i in range(3):
            cache.upsert(
                CachedEvent(
                    id=f"luma:{i}",
                    source="luma",
                    external_id=str(i),
                    title=f"Event {i}",
                )
            )
        assert cache.count() == 3

        deleted = cache.clear()
        assert deleted == 3
        assert cache.count() == 0

    def test_clear_by_source(self, cache):
        """Test clearing events from a specific source."""
        cache.upsert(
            CachedEvent(id="luma:1", source="luma", external_id="1", title="Luma 1")
        )
        cache.upsert(
            CachedEvent(
                id="eventbrite:1",
                source="eventbrite",
                external_id="1",
                title="EB 1",
            )
        )

        deleted = cache.clear(source="luma")
        assert deleted == 1
        assert cache.count("luma") == 0
        assert cache.count("eventbrite") == 1
