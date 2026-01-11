"""Tests for EventCache."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from api.services.event_cache import EventCache


class TestEventCache:
    """Test cases for EventCache."""

    @pytest.fixture
    def cache(self) -> Generator[EventCache]:
        """Create a cache with a temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            yield EventCache(db_path=db_path, ttl_hours=24)

    @pytest.fixture
    def sample_event(self) -> dict:
        """Create a sample event for testing."""
        return {
            "event_id": "evt-123",
            "title": "Tech Meetup",
            "date": "2026-01-15T18:00:00+00:00",
            "location": "Downtown Convention Center",
            "category": "tech",
            "description": "A meetup for tech enthusiasts",
            "is_free": True,
            "url": "https://example.com/event/123",
        }

    def test_put_and_get(self, cache: EventCache, sample_event: dict) -> None:
        """Test storing and retrieving an event."""
        cache.put(source="exa", **sample_event)

        result = cache.get("exa", "evt-123")

        assert result is not None
        assert result.event_id == "evt-123"
        assert result.title == "Tech Meetup"
        assert result.source == "exa"
        assert result.is_free is True

    def test_get_nonexistent(self, cache: EventCache) -> None:
        """Test getting a nonexistent event returns None."""
        result = cache.get("exa", "nonexistent")
        assert result is None

    def test_composite_key_different_sources(
        self, cache: EventCache, sample_event: dict
    ) -> None:
        """Test that same event_id with different sources are distinct."""
        cache.put(source="exa", **sample_event)

        exa_event = sample_event.copy()
        exa_event["title"] = "Exa Event"
        cache.put(source="exa", **exa_event)

        firecrawl_event = sample_event.copy()
        firecrawl_event["title"] = "Firecrawl Event"
        cache.put(source="firecrawl", **firecrawl_event)

        exa_result = cache.get("exa", "evt-123")
        firecrawl_result = cache.get("firecrawl", "evt-123")

        assert exa_result is not None
        assert firecrawl_result is not None
        assert exa_result.title == "Exa Event"
        assert firecrawl_result.title == "Firecrawl Event"

    def test_upsert_updates_existing(
        self, cache: EventCache, sample_event: dict
    ) -> None:
        """Test that putting an existing event updates it."""
        cache.put(source="exa", **sample_event)

        updated_event = sample_event.copy()
        updated_event["title"] = "Updated Meetup"
        cache.put(source="exa", **updated_event)

        result = cache.get("exa", "evt-123")

        assert result is not None
        assert result.title == "Updated Meetup"
        assert cache.count("exa") == 1

    def test_get_many(self, cache: EventCache) -> None:
        """Test retrieving multiple events."""
        for i in range(5):
            cache.put(
                source="exa",
                event_id=f"evt-{i}",
                title=f"Event {i}",
                date="2026-01-15T18:00:00+00:00",
                location="Location",
                category="tech",
                description="Description",
                is_free=True,
            )

        results = cache.get_many("exa", ["evt-0", "evt-2", "evt-4", "evt-999"])

        assert len(results) == 3
        event_ids = {e.event_id for e in results}
        assert event_ids == {"evt-0", "evt-2", "evt-4"}

    def test_put_many(self, cache: EventCache) -> None:
        """Test storing multiple events at once."""
        events = [
            {
                "event_id": f"evt-{i}",
                "title": f"Event {i}",
                "date": "2026-01-15T18:00:00+00:00",
                "location": "Location",
                "category": "tech",
                "description": "Description",
                "is_free": i % 2 == 0,
            }
            for i in range(10)
        ]

        count = cache.put_many("firecrawl", events)

        assert count == 10
        assert cache.count("firecrawl") == 10

    def test_clear_source(self, cache: EventCache) -> None:
        """Test clearing all events from a specific source."""
        cache.put(
            source="exa",
            event_id="evt-1",
            title="Exa Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )
        cache.put(
            source="firecrawl",
            event_id="evt-2",
            title="Firecrawl Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )

        deleted = cache.clear_source("exa")

        assert deleted == 1
        assert cache.get("exa", "evt-1") is None
        assert cache.get("firecrawl", "evt-2") is not None

    def test_clear_all(self, cache: EventCache) -> None:
        """Test clearing all cached events."""
        cache.put(
            source="exa",
            event_id="evt-1",
            title="Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )
        cache.put(
            source="firecrawl",
            event_id="evt-2",
            title="Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )

        deleted = cache.clear_all()

        assert deleted == 2
        assert cache.count() == 0

    def test_count(self, cache: EventCache) -> None:
        """Test counting cached events."""
        assert cache.count() == 0

        cache.put(
            source="exa",
            event_id="evt-1",
            title="Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )
        cache.put(
            source="exa",
            event_id="evt-2",
            title="Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )
        cache.put(
            source="firecrawl",
            event_id="evt-3",
            title="Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
        )

        assert cache.count() == 3
        assert cache.count("exa") == 2
        assert cache.count("firecrawl") == 1

    def test_raw_data_storage(self, cache: EventCache) -> None:
        """Test storing and retrieving raw_data."""
        raw_data = {"original_source": "api", "extra_field": "value"}

        cache.put(
            source="exa",
            event_id="evt-1",
            title="Event",
            date="2026-01-15T18:00:00+00:00",
            location="Location",
            category="tech",
            description="Description",
            is_free=True,
            raw_data=raw_data,
        )

        result = cache.get("exa", "evt-1")

        assert result is not None
        assert result.raw_data == raw_data


class TestEventCacheExpiry:
    """Test TTL and expiry functionality."""

    def test_expired_entry_returns_none(self) -> None:
        """Test that expired entries are not returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = EventCache(db_path=db_path, ttl_hours=0)

            cache.put(
                source="exa",
                event_id="evt-1",
                title="Event",
                date="2026-01-15T18:00:00+00:00",
                location="Location",
                category="tech",
                description="Description",
                is_free=True,
            )

            result = cache.get("exa", "evt-1")

            assert result is None

    def test_clear_expired(self) -> None:
        """Test clearing expired entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cache.db"
            cache = EventCache(db_path=db_path, ttl_hours=0)

            cache.put(
                source="exa",
                event_id="evt-1",
                title="Event",
                date="2026-01-15T18:00:00+00:00",
                location="Location",
                category="tech",
                description="Description",
                is_free=True,
            )

            deleted = cache.clear_expired()

            assert deleted == 1
            assert cache.count() == 0
