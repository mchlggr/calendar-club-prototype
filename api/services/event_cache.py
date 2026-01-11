"""
SQLite-based event cache for multi-source event storage.

Provides deduplication via composite keys and TTL-based expiration.
Used to cache events from Firecrawl/Luma, Eventbrite, and other sources.
"""

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Default cache location
DEFAULT_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "event_cache.db"

# Default TTL: 24 hours
DEFAULT_TTL_HOURS = 24


class CachedEvent(BaseModel):
    """Event stored in the cache."""

    id: str = Field(description="Unique ID (source:external_id)")
    source: str = Field(description="Event source: luma, eventbrite, etc.")
    external_id: str = Field(description="ID from the source system")
    title: str
    description: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    url: str | None = None
    category: str = "community"
    is_free: bool = True
    price_amount: int | None = None
    host_name: str | None = None
    cover_image_url: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    cached_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class EventCacheService:
    """SQLite-based cache for events from multiple sources.

    Features:
    - Composite-key deduplication (source + external_id)
    - TTL-based expiration (default 24h)
    - Query by source, location, date range
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ):
        """Initialize the event cache.

        Args:
            db_path: Path to SQLite database. Defaults to data/event_cache.db
            ttl_hours: Hours until cached events expire
        """
        if db_path is None:
            db_path = os.getenv("EVENT_CACHE_PATH", DEFAULT_CACHE_PATH)
        self.db_path = Path(db_path)
        self.ttl_hours = ttl_hours
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    start_time TEXT,
                    end_time TEXT,
                    location TEXT,
                    url TEXT,
                    category TEXT DEFAULT 'community',
                    is_free INTEGER DEFAULT 1,
                    price_amount INTEGER,
                    host_name TEXT,
                    cover_image_url TEXT,
                    raw_data TEXT DEFAULT '{}',
                    cached_at TEXT NOT NULL,
                    expires_at TEXT,
                    UNIQUE(source, external_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_expires_at ON events(expires_at)
            """)
            conn.commit()

    def _make_id(self, source: str, external_id: str) -> str:
        """Create composite ID from source and external ID."""
        return f"{source}:{external_id}"

    def upsert(self, event: CachedEvent) -> None:
        """Insert or update an event in the cache.

        Args:
            event: Event to cache
        """
        # Calculate expiration if not set
        if event.expires_at is None:
            event.expires_at = datetime.now(UTC) + timedelta(hours=self.ttl_hours)

        # Ensure ID is set correctly
        if not event.id or ":" not in event.id:
            event.id = self._make_id(event.source, event.external_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    id, source, external_id, title, description,
                    start_time, end_time, location, url, category,
                    is_free, price_amount, host_name, cover_image_url,
                    raw_data, cached_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.source,
                    event.external_id,
                    event.title,
                    event.description,
                    event.start_time.isoformat() if event.start_time else None,
                    event.end_time.isoformat() if event.end_time else None,
                    event.location,
                    event.url,
                    event.category,
                    1 if event.is_free else 0,
                    event.price_amount,
                    event.host_name,
                    event.cover_image_url,
                    json.dumps(event.raw_data),
                    event.cached_at.isoformat(),
                    event.expires_at.isoformat() if event.expires_at else None,
                ),
            )
            conn.commit()

    def upsert_many(self, events: list[CachedEvent]) -> int:
        """Insert or update multiple events.

        Args:
            events: List of events to cache

        Returns:
            Number of events upserted
        """
        for event in events:
            self.upsert(event)
        return len(events)

    def get_by_source(
        self,
        source: str,
        include_expired: bool = False,
        limit: int = 100,
    ) -> list[CachedEvent]:
        """Get events from a specific source.

        Args:
            source: Event source to filter by
            include_expired: Include expired events
            limit: Maximum number of events to return

        Returns:
            List of cached events
        """
        now = datetime.now(UTC).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if include_expired:
                cursor = conn.execute(
                    "SELECT * FROM events WHERE source = ? ORDER BY start_time LIMIT ?",
                    (source, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM events
                    WHERE source = ? AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY start_time LIMIT ?
                    """,
                    (source, now, limit),
                )

            return [self._row_to_event(row) for row in cursor.fetchall()]

    def search(
        self,
        sources: list[str] | None = None,
        start_after: datetime | None = None,
        start_before: datetime | None = None,
        location_contains: str | None = None,
        include_expired: bool = False,
        limit: int = 50,
    ) -> list[CachedEvent]:
        """Search cached events with filters.

        Args:
            sources: Filter by event sources
            start_after: Events starting after this time
            start_before: Events starting before this time
            location_contains: Location substring match (case-insensitive)
            include_expired: Include expired cache entries
            limit: Maximum number of results

        Returns:
            List of matching events
        """
        now = datetime.now(UTC).isoformat()
        conditions = []
        params: list[Any] = []

        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(now)

        if sources:
            placeholders = ",".join("?" * len(sources))
            conditions.append(f"source IN ({placeholders})")
            params.extend(sources)

        if start_after:
            conditions.append("start_time >= ?")
            params.append(start_after.isoformat())

        if start_before:
            conditions.append("start_time <= ?")
            params.append(start_before.isoformat())

        if location_contains:
            conditions.append("LOWER(location) LIKE ?")
            params.append(f"%{location_contains.lower()}%")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f"""
                SELECT * FROM events
                WHERE {where_clause}
                ORDER BY start_time
                LIMIT ?
                """,
                (*params, limit),
            )
            return [self._row_to_event(row) for row in cursor.fetchall()]

    def delete_expired(self) -> int:
        """Delete all expired events.

        Returns:
            Number of events deleted
        """
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            )
            conn.commit()
            return cursor.rowcount

    def clear(self, source: str | None = None) -> int:
        """Clear cached events.

        Args:
            source: If provided, only clear events from this source

        Returns:
            Number of events deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            if source:
                cursor = conn.execute("DELETE FROM events WHERE source = ?", (source,))
            else:
                cursor = conn.execute("DELETE FROM events")
            conn.commit()
            return cursor.rowcount

    def count(self, source: str | None = None) -> int:
        """Count cached events.

        Args:
            source: If provided, count only events from this source

        Returns:
            Number of events
        """
        with sqlite3.connect(self.db_path) as conn:
            if source:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE source = ?", (source,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM events")
            return cursor.fetchone()[0]

    def _row_to_event(self, row: sqlite3.Row) -> CachedEvent:
        """Convert a database row to CachedEvent."""
        return CachedEvent(
            id=row["id"],
            source=row["source"],
            external_id=row["external_id"],
            title=row["title"],
            description=row["description"] or "",
            start_time=datetime.fromisoformat(row["start_time"])
            if row["start_time"]
            else None,
            end_time=datetime.fromisoformat(row["end_time"])
            if row["end_time"]
            else None,
            location=row["location"],
            url=row["url"],
            category=row["category"] or "community",
            is_free=bool(row["is_free"]),
            price_amount=row["price_amount"],
            host_name=row["host_name"],
            cover_image_url=row["cover_image_url"],
            raw_data=json.loads(row["raw_data"]) if row["raw_data"] else {},
            cached_at=datetime.fromisoformat(row["cached_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"])
            if row["expires_at"]
            else None,
        )


# Singleton instance
_cache_service: EventCacheService | None = None


def get_event_cache() -> EventCacheService:
    """Get the singleton event cache service."""
    global _cache_service
    if _cache_service is None:
        _cache_service = EventCacheService()
    return _cache_service
