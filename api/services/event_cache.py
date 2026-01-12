"""
SQLite-based event cache for deduplication across search providers.

Provides caching with composite-key deduplication (source + event_id) and
24-hour TTL. Shared by Exa, Firecrawl, and other event search sources.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Default database path (relative to api root)
DEFAULT_CACHE_DB_PATH = Path(__file__).parent.parent / "event_cache.db"

# Default TTL: 24 hours
DEFAULT_TTL_HOURS = 24


class CachedEvent(BaseModel):
    """Event data stored in cache."""

    source: str
    event_id: str
    title: str
    date: str
    location: str
    category: str
    description: str
    is_free: bool
    price_amount: int | None = None
    url: str | None = None
    logo_url: str | None = None
    raw_data: dict[str, Any] | None = None
    cached_at: datetime


class EventCache:
    """
    SQLite-based event cache with composite-key deduplication.

    Uses source + event_id as composite key for deduplication across
    different search providers (Exa, Firecrawl, etc.).

    Thread-safe for concurrent access.

    Usage:
        cache = EventCache()
        cache.put("exa", event)
        cached = cache.get("exa", "event-123")
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        ttl_hours: int = DEFAULT_TTL_HOURS,
    ):
        """
        Initialize the event cache.

        Args:
            db_path: Path to SQLite database file. Defaults to api/event_cache.db
            ttl_hours: Time-to-live for cached entries in hours. Defaults to 24.
        """
        self.db_path = str(db_path or DEFAULT_CACHE_DB_PATH)
        self.ttl_hours = ttl_hours
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    source TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    date TEXT NOT NULL,
                    location TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    is_free INTEGER NOT NULL,
                    price_amount INTEGER,
                    url TEXT,
                    logo_url TEXT,
                    raw_data TEXT,
                    cached_at TEXT NOT NULL,
                    PRIMARY KEY (source, event_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cached_at
                ON events (cached_at)
            """)
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _is_expired(self, cached_at: str) -> bool:
        """Check if a cached entry has expired."""
        cached_time = datetime.fromisoformat(cached_at)
        expiry = cached_time + timedelta(hours=self.ttl_hours)
        return datetime.now(timezone.utc) > expiry

    def _row_to_event(self, row: sqlite3.Row | None) -> CachedEvent | None:
        """Convert a database row to CachedEvent."""
        if row is None:
            return None

        if self._is_expired(row["cached_at"]):
            return None

        raw_data = None
        if row["raw_data"]:
            try:
                raw_data = json.loads(row["raw_data"])
            except json.JSONDecodeError:
                pass

        return CachedEvent(
            source=row["source"],
            event_id=row["event_id"],
            title=row["title"],
            date=row["date"],
            location=row["location"],
            category=row["category"],
            description=row["description"],
            is_free=bool(row["is_free"]),
            price_amount=row["price_amount"],
            url=row["url"],
            logo_url=row["logo_url"],
            raw_data=raw_data,
            cached_at=datetime.fromisoformat(row["cached_at"]),
        )

    def get(self, source: str, event_id: str) -> CachedEvent | None:
        """
        Get a cached event by source and event_id.

        Args:
            source: The event source (e.g., "exa", "firecrawl", "eventbrite")
            event_id: The event's unique ID within the source

        Returns:
            CachedEvent if found and not expired, None otherwise
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM events WHERE source = ? AND event_id = ?",
                    (source, event_id),
                )
                row = cursor.fetchone()
                return self._row_to_event(row)

    def get_many(self, source: str, event_ids: list[str]) -> list[CachedEvent]:
        """
        Get multiple cached events by source and event_ids.

        Args:
            source: The event source
            event_ids: List of event IDs to retrieve

        Returns:
            List of cached events (excludes missing/expired entries)
        """
        if not event_ids:
            return []

        with self._lock:
            with self._get_connection() as conn:
                placeholders = ",".join("?" * len(event_ids))
                cursor = conn.execute(
                    f"SELECT * FROM events WHERE source = ? AND event_id IN ({placeholders})",
                    [source, *event_ids],
                )
                events = []
                for row in cursor.fetchall():
                    event = self._row_to_event(row)
                    if event:
                        events.append(event)
                return events

    def put(
        self,
        source: str,
        event_id: str,
        title: str,
        date: str,
        location: str,
        category: str,
        description: str,
        is_free: bool,
        price_amount: int | None = None,
        url: str | None = None,
        logo_url: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Cache an event (upsert).

        Args:
            source: The event source (e.g., "exa", "firecrawl")
            event_id: The event's unique ID
            title: Event title
            date: ISO 8601 datetime string
            location: Venue/location string
            category: Event category
            description: Event description
            is_free: Whether the event is free
            price_amount: Price in cents (optional)
            url: Event URL (optional)
            logo_url: Event logo/image URL (optional)
            raw_data: Original raw data dict for debugging (optional)
        """
        cached_at = datetime.now(timezone.utc).isoformat()
        raw_data_json = json.dumps(raw_data) if raw_data else None

        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events
                    (source, event_id, title, date, location, category,
                     description, is_free, price_amount, url, logo_url,
                     raw_data, cached_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source,
                        event_id,
                        title,
                        date,
                        location,
                        category,
                        description,
                        int(is_free),
                        price_amount,
                        url,
                        logo_url,
                        raw_data_json,
                        cached_at,
                    ),
                )
                conn.commit()

    def put_event(self, source: str, event: CachedEvent) -> None:
        """
        Cache a CachedEvent object.

        Args:
            source: The event source
            event: CachedEvent to cache
        """
        self.put(
            source=source,
            event_id=event.event_id,
            title=event.title,
            date=event.date,
            location=event.location,
            category=event.category,
            description=event.description,
            is_free=event.is_free,
            price_amount=event.price_amount,
            url=event.url,
            logo_url=event.logo_url,
            raw_data=event.raw_data,
        )

    def put_many(
        self, source: str, events: list[dict[str, Any]]
    ) -> int:
        """
        Cache multiple events in a single transaction.

        Args:
            source: The event source
            events: List of event dicts with keys matching put() parameters

        Returns:
            Number of events cached
        """
        if not events:
            return 0

        cached_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                for event in events:
                    raw_data_json = (
                        json.dumps(event.get("raw_data"))
                        if event.get("raw_data")
                        else None
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO events
                        (source, event_id, title, date, location, category,
                         description, is_free, price_amount, url, logo_url,
                         raw_data, cached_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source,
                            event["event_id"],
                            event["title"],
                            event["date"],
                            event["location"],
                            event["category"],
                            event["description"],
                            int(event.get("is_free", True)),
                            event.get("price_amount"),
                            event.get("url"),
                            event.get("logo_url"),
                            raw_data_json,
                            cached_at,
                        ),
                    )
                conn.commit()
                return len(events)

    def clear_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)
        ).isoformat()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM events WHERE cached_at < ?",
                    (cutoff,),
                )
                conn.commit()
                deleted = cursor.rowcount
                if deleted > 0:
                    logger.info("Cleared %d expired cache entries", deleted)
                return deleted

    def clear_source(self, source: str) -> int:
        """
        Clear all cached events from a specific source.

        Args:
            source: The event source to clear

        Returns:
            Number of entries removed
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM events WHERE source = ?",
                    (source,),
                )
                conn.commit()
                return cursor.rowcount

    def clear_all(self) -> int:
        """
        Clear all cached events.

        Returns:
            Number of entries removed
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM events")
                conn.commit()
                return cursor.rowcount

    def count(self, source: str | None = None) -> int:
        """
        Count cached events.

        Args:
            source: Optional source to filter by

        Returns:
            Number of cached events
        """
        with self._lock:
            with self._get_connection() as conn:
                if source:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM events WHERE source = ?",
                        (source,),
                    )
                else:
                    cursor = conn.execute("SELECT COUNT(*) FROM events")
                return cursor.fetchone()[0]


# Global cache instance
_cache: EventCache | None = None


def get_event_cache() -> EventCache:
    """
    Get the global event cache instance.

    Returns a singleton EventCache for dependency injection in FastAPI.
    """
    global _cache
    if _cache is None:
        _cache = EventCache()
    return _cache


def init_event_cache(
    db_path: str | Path | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> EventCache:
    """
    Initialize the global event cache with custom settings.

    Call this at application startup if you need a custom database path.

    Args:
        db_path: Custom path for the SQLite database
        ttl_hours: Custom TTL in hours

    Returns:
        The initialized EventCache
    """
    global _cache
    _cache = EventCache(db_path=db_path, ttl_hours=ttl_hours)
    return _cache


# Alias for backward compatibility
EventCacheService = EventCache
