# Exa.ai Websets Integration Implementation Plan

## Overview

Integrate Exa.ai into the Calendar Club event discovery workflow with a **hybrid fast+deep pattern**. This provides instant results via Exa Search API alongside Eventbrite, while Exa Websets runs asynchronously to discover additional verified events. Results are cached in SQLite for efficiency and inline updates notify users when deeper discovery completes.

## Current State Analysis

**Existing Architecture:**
- Two-phase agent workflow: ClarifyingAgent → Search phase (`api/index.py:111-197`)
- Single event source: Eventbrite API (`api/services/eventbrite.py`)
- Streaming via SSE to frontend (`api/index.py:104-108`)
- Location hardcoded to Columbus, OH (`api/agents/search.py:70`)
- OpenAI Agents SDK for orchestration (`agents` package)

**Key Files:**
- `api/agents/search.py:124-166` - `search_events()` function
- `api/services/eventbrite.py:35-57` - `EventbriteClient` pattern
- `api/config.py:12-44` - Settings with environment variables
- `api/models/search.py:30-45` - `SearchProfile` model

### Key Discoveries:
- `EventbriteClient` uses `httpx.AsyncClient` with lazy initialization (`eventbrite.py:44-51`)
- Singleton pattern via module-level `_client` variable (`eventbrite.py:222-231`)
- `SearchResult` model has `source` field for attribution (`search.py:54-61`)
- SSE events include type in JSON payload (`index.py:104-108`)
- No existing caching layer for events

## Desired End State

After implementation:
1. User searches trigger parallel queries to Eventbrite + Exa Search API
2. Results from both sources display immediately (deduped, source-attributed)
3. Websets async job starts in background for deeper discovery
4. When Websets completes, new events stream to frontend via inline SSE update
5. All discovered events cached in SQLite with 24-hour TTL
6. Subsequent searches check cache first, reducing API costs

**Verification:**
- `pytest api/` passes with new tests
- Manual test: Search returns events from both sources
- Manual test: Websets results appear after delay with "More events found" indicator
- Cache hit rate visible in logs

## What We're NOT Doing

- Webhook integration (polling is simpler for MVP)
- Monitors for continuous discovery (future enhancement)
- Location extraction from user input (keep Columbus, OH default)
- Frontend UI changes beyond handling new SSE event types
- Exa Research API integration (only Search + Websets)

## Implementation Approach

**Hybrid Fast+Deep Pattern:**
```
User Query
    │
    ├──► Eventbrite API ──────► Instant Results (500ms)
    │
    ├──► Exa Search API ──────► Instant Results (500ms)
    │
    └──► Exa Websets ─────────► Deep Results (minutes)
              │                      │
              └── Poll/Background ───┘
                        │
                        ▼
              Inline SSE Update ("more_events")
```

**Data Flow:**
1. Check SQLite cache for matching events
2. If cache miss or stale, query Eventbrite + Exa Search in parallel
3. Deduplicate by URL/title similarity
4. Store in cache, return to user
5. Start Websets background task
6. Poll Websets, when complete: cache results, send SSE update

---

## Phase 1: Exa Client & Configuration

### Overview
Create the foundational Exa client following the established `EventbriteClient` pattern.

### Changes Required:

#### 1.1 Configuration

**File**: `api/config.py`
**Changes**: Add Exa API key to Settings

```python
class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Required
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Event sources
    eventbrite_api_key: str = Field(default="", description="Eventbrite API key")
    exa_api_key: str = Field(default="", description="Exa.ai API key")

    # ... rest unchanged ...

    @property
    def has_event_source(self) -> bool:
        """Check if any event source is configured."""
        return bool(self.eventbrite_api_key) or bool(self.exa_api_key)
```

#### 1.2 Exa Client

**File**: `api/services/exa_client.py` (new file)
**Changes**: Create async HTTP client for Exa APIs

```python
"""
Exa.ai API client for event discovery.

Provides async methods for both Search API (fast) and Websets API (async/deep).
"""

import logging
import os
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ExaEvent(BaseModel):
    """Parsed event from Exa API."""

    id: str
    title: str
    description: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    category: str = "community"
    is_free: bool | None = None
    price_amount: int | None = None
    url: str
    image_url: str | None = None


class ExaSearchResult(BaseModel):
    """Result from Exa Search API."""

    events: list[ExaEvent]
    source: str = "exa_search"


class WebsetStatus(BaseModel):
    """Status of an Exa Webset."""

    id: str
    status: str  # "running", "idle", "paused"
    item_count: int = 0


class ExaClient:
    """Async client for Exa.ai APIs."""

    SEARCH_BASE_URL = "https://api.exa.ai"
    WEBSETS_BASE_URL = "https://api.exa.ai/websets/v0"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        self._search_client: httpx.AsyncClient | None = None
        self._websets_client: httpx.AsyncClient | None = None

    async def _get_search_client(self) -> httpx.AsyncClient:
        if self._search_client is None:
            self._search_client = httpx.AsyncClient(
                base_url=self.SEARCH_BASE_URL,
                headers={"x-api-key": self.api_key},
                timeout=30.0,
            )
        return self._search_client

    async def _get_websets_client(self) -> httpx.AsyncClient:
        if self._websets_client is None:
            self._websets_client = httpx.AsyncClient(
                base_url=self.WEBSETS_BASE_URL,
                headers={"x-api-key": self.api_key},
                timeout=60.0,  # Longer timeout for websets
            )
        return self._websets_client

    async def close(self) -> None:
        """Close HTTP clients."""
        if self._search_client:
            await self._search_client.aclose()
            self._search_client = None
        if self._websets_client:
            await self._websets_client.aclose()
            self._websets_client = None

    async def search_events(
        self,
        query: str,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        num_results: int = 10,
    ) -> ExaSearchResult:
        """
        Search for events using Exa Search API (fast, synchronous).

        Args:
            query: Natural language search query
            location: Location to search in (e.g., "Columbus, OH")
            start_date: Filter events after this date
            end_date: Filter events before this date
            num_results: Number of results to return

        Returns:
            ExaSearchResult with list of events
        """
        if not self.api_key:
            return ExaSearchResult(events=[], source="exa_search")

        client = await self._get_search_client()

        # Build search query with location and date context
        full_query = f"in-person events {query}"
        if location:
            full_query += f" in {location}"
        if start_date:
            full_query += f" after {start_date.strftime('%B %Y')}"

        # Event extraction schema
        event_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "date": {"type": "string"},
                "venue": {"type": "string"},
                "address": {"type": "string"},
                "price": {"type": "string"},
                "image_url": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["name"],
        }

        payload = {
            "query": full_query,
            "num_results": num_results,
            "use_autoprompt": True,
            "summary": {
                "query": "Extract event details: name, date, venue, address, price, image URL, brief summary",
                "schema": event_schema,
            },
        }

        # Add date filter if provided
        if start_date:
            payload["start_published_date"] = start_date.strftime("%Y-%m-%d")

        try:
            response = await client.post("/search", json=payload)
            response.raise_for_status()
            data = response.json()

            events = []
            for result in data.get("results", []):
                event = self._parse_search_result(result)
                if event:
                    events.append(event)

            return ExaSearchResult(events=events, source="exa_search")

        except httpx.HTTPError as e:
            logger.warning("Exa Search API error: %s", e)
            return ExaSearchResult(events=[], source="exa_search")

    def _parse_search_result(self, result: dict[str, Any]) -> ExaEvent | None:
        """Parse Exa Search API result into ExaEvent."""
        try:
            import json

            # Parse the summary JSON
            summary_str = result.get("summary", "{}")
            try:
                summary = json.loads(summary_str)
            except json.JSONDecodeError:
                summary = {}

            # Extract event details
            title = summary.get("name") or result.get("title", "Untitled Event")

            # Parse date if available
            start_time = None
            date_str = summary.get("date")
            if date_str:
                try:
                    # Try common date formats
                    from dateutil import parser
                    start_time = parser.parse(date_str)
                except Exception:
                    pass

            return ExaEvent(
                id=result.get("id", result.get("url", "")),
                title=title,
                description=summary.get("summary", result.get("text", ""))[:500],
                start_time=start_time,
                venue_name=summary.get("venue"),
                venue_address=summary.get("address"),
                is_free="free" in summary.get("price", "").lower() if summary.get("price") else None,
                url=result.get("url", ""),
                image_url=summary.get("image_url") or result.get("image"),
            )

        except Exception as e:
            logger.warning("Error parsing Exa search result: %s", e)
            return None

    async def create_webset(
        self,
        query: str,
        location: str,
        count: int = 20,
    ) -> str | None:
        """
        Create an Exa Webset for deep event discovery.

        Args:
            query: Natural language query for events
            location: Location to search in
            count: Number of results to find

        Returns:
            Webset ID if created successfully, None otherwise
        """
        if not self.api_key:
            return None

        client = await self._get_websets_client()

        payload = {
            "search": {
                "query": f"In-person events: {query} in {location}",
                "count": count,
            },
            "criteria": [
                {"description": "Event is in-person (not virtual or online)"},
                {"description": f"Event takes place in or near {location}"},
                {"description": "Result is an actual event page, not a news article or blog post"},
                {"description": "Event has not already passed"},
            ],
            "enrichments": [
                {"description": "Event name/title", "format": "text"},
                {"description": "Event start date and time", "format": "date"},
                {"description": "Event end date and time", "format": "date"},
                {"description": "Venue name", "format": "text"},
                {"description": "Full address including city and state", "format": "text"},
                {"description": "Ticket price in USD (lowest tier, or 'Free')", "format": "text"},
                {"description": "Event registration or ticket URL", "format": "url"},
                {"description": "Event banner or poster image URL", "format": "url"},
                {"description": "Brief event description (1-2 sentences)", "format": "text"},
            ],
        }

        try:
            response = await client.post("/websets", json=payload)
            response.raise_for_status()
            data = response.json()
            webset_id = data.get("id")
            logger.info("Created Exa Webset: %s", webset_id)
            return webset_id

        except httpx.HTTPError as e:
            logger.warning("Exa Websets API error: %s", e)
            return None

    async def get_webset_status(self, webset_id: str) -> WebsetStatus | None:
        """Get the status of a Webset."""
        if not self.api_key:
            return None

        client = await self._get_websets_client()

        try:
            response = await client.get(f"/websets/{webset_id}")
            response.raise_for_status()
            data = response.json()

            return WebsetStatus(
                id=webset_id,
                status=data.get("status", "unknown"),
                item_count=data.get("itemCount", 0),
            )

        except httpx.HTTPError as e:
            logger.warning("Error getting Webset status: %s", e)
            return None

    async def get_webset_items(self, webset_id: str) -> list[ExaEvent]:
        """Get items from a completed Webset."""
        if not self.api_key:
            return []

        client = await self._get_websets_client()

        try:
            response = await client.get(f"/websets/{webset_id}/items")
            response.raise_for_status()
            data = response.json()

            events = []
            for item in data.get("data", []):
                event = self._parse_webset_item(item)
                if event:
                    events.append(event)

            return events

        except httpx.HTTPError as e:
            logger.warning("Error getting Webset items: %s", e)
            return []

    def _parse_webset_item(self, item: dict[str, Any]) -> ExaEvent | None:
        """Parse Webset item with enrichments into ExaEvent."""
        try:
            enrichments = {e.get("description", ""): e.get("value") for e in item.get("enrichments", [])}

            # Parse dates
            start_time = None
            start_str = enrichments.get("Event start date and time")
            if start_str:
                try:
                    from dateutil import parser
                    start_time = parser.parse(start_str)
                except Exception:
                    pass

            end_time = None
            end_str = enrichments.get("Event end date and time")
            if end_str:
                try:
                    from dateutil import parser
                    end_time = parser.parse(end_str)
                except Exception:
                    pass

            # Parse price
            price_str = enrichments.get("Ticket price in USD (lowest tier, or 'Free')", "")
            is_free = "free" in price_str.lower() if price_str else None
            price_amount = None
            if price_str and not is_free:
                import re
                match = re.search(r"\d+", price_str)
                if match:
                    price_amount = int(match.group())

            return ExaEvent(
                id=item.get("id", item.get("url", "")),
                title=enrichments.get("Event name/title", "Untitled Event"),
                description=enrichments.get("Brief event description (1-2 sentences)", "")[:500],
                start_time=start_time,
                end_time=end_time,
                venue_name=enrichments.get("Venue name"),
                venue_address=enrichments.get("Full address including city and state"),
                is_free=is_free,
                price_amount=price_amount,
                url=item.get("url", ""),
                image_url=enrichments.get("Event banner or poster image URL"),
            )

        except Exception as e:
            logger.warning("Error parsing Webset item: %s", e)
            return None


# Singleton instance
_client: ExaClient | None = None


def get_exa_client() -> ExaClient:
    """Get the singleton Exa client."""
    global _client
    if _client is None:
        _client = ExaClient()
    return _client
```

#### 1.3 Services Module Export

**File**: `api/services/__init__.py`
**Changes**: Export new Exa client

```python
from api.services.eventbrite import EventbriteClient, get_eventbrite_client
from api.services.exa_client import ExaClient, get_exa_client

__all__ = [
    "EventbriteClient",
    "get_eventbrite_client",
    "ExaClient",
    "get_exa_client",
]
```

### Success Criteria:

#### Automated Verification:
- [ ] Type checking passes: `cd api && python -m mypy services/exa_client.py`
- [ ] Unit tests pass: `pytest api/services/tests/test_exa_client.py -v`
- [ ] Import works: `python -c "from api.services import get_exa_client"`

#### Manual Verification:
- [ ] With valid EXA_API_KEY, `search_events()` returns results
- [ ] Without API key, methods return empty results gracefully

**Implementation Note**: After completing this phase, proceed to Phase 2.

---

## Phase 2: Multi-Source Search Integration

### Overview
Modify the search flow to query both Eventbrite and Exa Search API in parallel, with deduplication.

### Changes Required:

#### 2.1 Update Search Models

**File**: `api/agents/search.py`
**Changes**: Add source tracking and multi-source support

```python
# Add to existing EventResult model
class EventResult(BaseModel):
    """An event from search results."""

    id: str
    title: str
    date: str = Field(description="ISO 8601 datetime string")
    location: str
    category: str
    description: str
    is_free: bool
    price_amount: int | None = None
    distance_miles: float
    url: str | None = None
    image_url: str | None = None  # NEW: Add image URL
    source: str = Field(default="unknown", description="Data source: eventbrite, exa_search, exa_websets")


class SearchResult(BaseModel):
    """Result from search_events tool."""

    events: list[EventResult]
    source: str = Field(description="Primary data source")
    sources_queried: list[str] = Field(default_factory=list, description="All sources that were queried")
    message: str | None = Field(default=None, description="User-facing message")
```

#### 2.2 Multi-Source Search Function

**File**: `api/agents/search.py`
**Changes**: Update `search_events()` to query multiple sources

```python
import asyncio
from api.services import get_eventbrite_client, get_exa_client


async def _fetch_exa_search_events(profile: SearchProfile) -> list[EventResult]:
    """Fetch events from Exa Search API."""
    client = get_exa_client()

    # Build query from profile
    query_parts = []
    if profile.categories:
        query_parts.extend(profile.categories)
    if profile.keywords:
        query_parts.extend(profile.keywords)
    if not query_parts:
        query_parts = ["community events", "meetups"]

    query = " ".join(query_parts)
    location = "Columbus, OH"  # Default location

    # Parse time window
    start_date = None
    if profile.time_window and profile.time_window.start:
        start_value = profile.time_window.start
        if isinstance(start_value, str):
            start_date = datetime.fromisoformat(start_value)
        else:
            start_date = start_value

    result = await client.search_events(
        query=query,
        location=location,
        start_date=start_date,
        num_results=10,
    )

    # Convert to EventResult format
    events = []
    for event in result.events:
        venue = event.venue_name or "TBD"
        if event.venue_address:
            venue = f"{venue}, {event.venue_address}"

        events.append(
            EventResult(
                id=f"exa_{event.id}",
                title=event.title,
                date=event.start_time.isoformat() if event.start_time else "",
                location=venue,
                category=event.category,
                description=event.description[:200] if event.description else "",
                is_free=event.is_free if event.is_free is not None else True,
                price_amount=event.price_amount,
                distance_miles=5.0,
                url=event.url,
                image_url=event.image_url,
                source="exa_search",
            )
        )

    return events


def _deduplicate_events(events: list[EventResult]) -> list[EventResult]:
    """Remove duplicate events based on URL and title similarity."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for event in events:
        # Check URL
        if event.url and event.url in seen_urls:
            continue

        # Check title similarity (simple normalization)
        title_normalized = event.title.lower().strip()
        if title_normalized in seen_titles:
            continue

        if event.url:
            seen_urls.add(event.url)
        seen_titles.add(title_normalized)
        unique.append(event)

    return unique


async def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile from multiple sources.

    Args:
        profile: SearchProfile with categories, time_window, constraints

    Returns:
        SearchResult with deduplicated events from all sources
    """
    settings = get_settings()
    sources_queried = []
    all_events = []

    # Build list of search tasks
    tasks = []

    if settings.eventbrite_api_key:
        sources_queried.append("eventbrite")
        tasks.append(_fetch_eventbrite_events(profile))

    if settings.exa_api_key:
        sources_queried.append("exa_search")
        tasks.append(_fetch_exa_search_events(profile))

    if not tasks:
        logger.warning("No event sources configured")
        return SearchResult(
            events=[],
            source="unavailable",
            sources_queried=[],
            message="Event search is not currently available.",
        )

    # Execute searches in parallel
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Search error from %s: %s", sources_queried[i], result)
                continue
            all_events.extend(result)

    except Exception as e:
        logger.error("Multi-source search error: %s", e, exc_info=True)
        return SearchResult(
            events=[],
            source="unavailable",
            sources_queried=sources_queried,
            message="Event search encountered an error. Please try again.",
        )

    # Deduplicate events
    unique_events = _deduplicate_events(all_events)

    # Sort by date (events with dates first)
    unique_events.sort(key=lambda e: (e.date == "", e.date))

    if unique_events:
        # Determine primary source (most events)
        source_counts = {}
        for evt in unique_events:
            source_counts[evt.source] = source_counts.get(evt.source, 0) + 1
        primary_source = max(source_counts, key=source_counts.get)

        logger.info("Found %s events from %s sources", len(unique_events), len(sources_queried))
        return SearchResult(
            events=unique_events,
            source=primary_source,
            sources_queried=sources_queried,
            message=None,
        )

    return SearchResult(
        events=[],
        source="none",
        sources_queried=sources_queried,
        message="No events found matching your criteria. Try broadening your search.",
    )
```

#### 2.3 Update SSE Event Format

**File**: `api/index.py`
**Changes**: Include source and image_url in event data

```python
# In stream_chat_response(), update the events_data construction:
events_data = [
    {
        "id": evt.id,
        "title": evt.title,
        "startTime": evt.date,
        "location": evt.location,
        "categories": [evt.category],
        "url": evt.url,
        "imageUrl": evt.image_url,  # NEW
        "source": evt.source,  # Changed from search_result.source
    }
    for evt in search_result.events
]
```

### Success Criteria:

#### Automated Verification:
- [ ] Unit tests pass: `pytest api/agents/tests/test_search.py -v`
- [ ] Type checking passes: `cd api && python -m mypy agents/search.py`

#### Manual Verification:
- [ ] With both API keys: Search returns events from both sources
- [ ] With only Eventbrite key: Search returns only Eventbrite events
- [ ] With only Exa key: Search returns only Exa events
- [ ] Duplicate events (same URL) appear only once

**Implementation Note**: After completing this phase, proceed to Phase 3.

---

## Phase 3: SQLite Event Cache

### Overview
Add a caching layer to reduce API costs and improve response times for repeated queries.

### Changes Required:

#### 3.1 Event Cache Service

**File**: `api/services/event_cache.py` (new file)
**Changes**: Create SQLite-based event cache

```python
"""
Event caching service for Calendar Club.

Caches discovered events in SQLite to reduce API costs and improve latency.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DB = Path(__file__).parent.parent / "event_cache.db"
DEFAULT_TTL_HOURS = 24


class CachedEvent(BaseModel):
    """Event stored in cache."""

    id: str
    title: str
    date: str
    location: str
    category: str
    description: str
    is_free: bool
    price_amount: int | None = None
    url: str | None = None
    image_url: str | None = None
    source: str
    cached_at: datetime
    query_hash: str


class EventCache:
    """SQLite-based event cache."""

    def __init__(self, db_path: str | Path | None = None, ttl_hours: int = DEFAULT_TTL_HOURS):
        self.db_path = str(db_path or DEFAULT_CACHE_DB)
        self.ttl_hours = ttl_hours
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    date TEXT,
                    location TEXT,
                    category TEXT,
                    description TEXT,
                    is_free INTEGER,
                    price_amount INTEGER,
                    url TEXT,
                    image_url TEXT,
                    source TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    query_hash TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_query_hash ON events(query_hash)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cached_at ON events(cached_at)
            """)
            conn.commit()

    def _make_query_hash(self, categories: list[str], location: str, date_start: str | None) -> str:
        """Create a hash key for a query."""
        import hashlib
        key = f"{sorted(categories)}:{location}:{date_start or ''}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def get_cached_events(
        self,
        categories: list[str],
        location: str,
        date_start: str | None = None,
    ) -> list[CachedEvent] | None:
        """
        Get cached events for a query.

        Returns None if no cache or cache is stale.
        """
        query_hash = self._make_query_hash(categories, location, date_start)
        cutoff = datetime.utcnow() - timedelta(hours=self.ttl_hours)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM events
                WHERE query_hash = ? AND cached_at > ?
                ORDER BY date ASC
                """,
                (query_hash, cutoff.isoformat()),
            )
            rows = cursor.fetchall()

        if not rows:
            return None

        return [
            CachedEvent(
                id=row["id"],
                title=row["title"],
                date=row["date"] or "",
                location=row["location"] or "",
                category=row["category"] or "",
                description=row["description"] or "",
                is_free=bool(row["is_free"]),
                price_amount=row["price_amount"],
                url=row["url"],
                image_url=row["image_url"],
                source=row["source"],
                cached_at=datetime.fromisoformat(row["cached_at"]),
                query_hash=row["query_hash"],
            )
            for row in rows
        ]

    def cache_events(
        self,
        events: list[dict[str, Any]],
        categories: list[str],
        location: str,
        date_start: str | None = None,
    ) -> None:
        """Cache events for a query."""
        query_hash = self._make_query_hash(categories, location, date_start)
        cached_at = datetime.utcnow().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            for event in events:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events
                    (id, title, date, location, category, description,
                     is_free, price_amount, url, image_url, source, cached_at, query_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.get("id"),
                        event.get("title"),
                        event.get("date"),
                        event.get("location"),
                        event.get("category"),
                        event.get("description"),
                        int(event.get("is_free", True)),
                        event.get("price_amount"),
                        event.get("url"),
                        event.get("image_url"),
                        event.get("source"),
                        cached_at,
                        query_hash,
                    ),
                )
            conn.commit()
            logger.info("Cached %s events for query %s", len(events), query_hash)

    def cleanup_stale(self) -> int:
        """Remove stale cache entries. Returns count of deleted rows."""
        cutoff = datetime.utcnow() - timedelta(hours=self.ttl_hours)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE cached_at < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()
            return cursor.rowcount


# Singleton instance
_cache: EventCache | None = None


def get_event_cache() -> EventCache:
    """Get the singleton event cache."""
    global _cache
    if _cache is None:
        _cache = EventCache()
    return _cache
```

#### 3.2 Integrate Cache with Search

**File**: `api/agents/search.py`
**Changes**: Check cache before API calls

```python
from api.services.event_cache import get_event_cache


async def search_events(profile: SearchProfile) -> SearchResult:
    """Search with cache support."""
    settings = get_settings()
    cache = get_event_cache()

    # Build cache key components
    categories = profile.categories or []
    location = "Columbus, OH"
    date_start = None
    if profile.time_window and profile.time_window.start:
        start_value = profile.time_window.start
        if isinstance(start_value, str):
            date_start = start_value
        else:
            date_start = start_value.isoformat()

    # Check cache first
    cached = cache.get_cached_events(categories, location, date_start)
    if cached:
        logger.info("Cache hit: %s events", len(cached))
        events = [
            EventResult(
                id=e.id,
                title=e.title,
                date=e.date,
                location=e.location,
                category=e.category,
                description=e.description,
                is_free=e.is_free,
                price_amount=e.price_amount,
                distance_miles=5.0,
                url=e.url,
                image_url=e.image_url,
                source=e.source,
            )
            for e in cached
        ]
        return SearchResult(
            events=events,
            source="cache",
            sources_queried=["cache"],
            message=None,
        )

    # Cache miss - fetch from APIs
    # ... (existing multi-source search code) ...

    # After getting results, cache them
    if unique_events:
        cache.cache_events(
            [
                {
                    "id": e.id,
                    "title": e.title,
                    "date": e.date,
                    "location": e.location,
                    "category": e.category,
                    "description": e.description,
                    "is_free": e.is_free,
                    "price_amount": e.price_amount,
                    "url": e.url,
                    "image_url": e.image_url,
                    "source": e.source,
                }
                for e in unique_events
            ],
            categories,
            location,
            date_start,
        )

    return SearchResult(...)
```

### Success Criteria:

#### Automated Verification:
- [ ] Unit tests pass: `pytest api/services/tests/test_event_cache.py -v`
- [ ] Cache database created: `ls api/event_cache.db`

#### Manual Verification:
- [ ] First search: logs show API calls
- [ ] Second identical search: logs show "Cache hit"
- [ ] After 24 hours (or manual TTL change): cache miss, fresh API calls

**Implementation Note**: After completing this phase, proceed to Phase 4.

---

## Phase 4: Websets Async Deep Discovery

### Overview
Implement background Websets discovery with polling and inline SSE updates.

### Changes Required:

#### 4.1 Background Task Manager

**File**: `api/services/background_tasks.py` (new file)
**Changes**: Manage async Websets polling

```python
"""
Background task manager for async operations like Websets polling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Callable, Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class WebsetTask(BaseModel):
    """Tracking info for a Websets background task."""

    webset_id: str
    session_id: str
    query: str
    location: str
    created_at: datetime
    status: str = "pending"  # pending, polling, complete, failed


class BackgroundTaskManager:
    """Manages background async tasks."""

    def __init__(self):
        self._tasks: dict[str, WebsetTask] = {}
        self._callbacks: dict[str, Callable] = {}
        self._running = False

    def start_webset_task(
        self,
        webset_id: str,
        session_id: str,
        query: str,
        location: str,
        on_complete: Callable[[str, list], Any] | None = None,
    ) -> None:
        """Start tracking a Webset and poll for completion."""
        task = WebsetTask(
            webset_id=webset_id,
            session_id=session_id,
            query=query,
            location=location,
            created_at=datetime.utcnow(),
        )
        self._tasks[webset_id] = task

        if on_complete:
            self._callbacks[webset_id] = on_complete

        # Start polling in background
        asyncio.create_task(self._poll_webset(webset_id))

    async def _poll_webset(self, webset_id: str, max_polls: int = 60, interval: int = 30) -> None:
        """Poll Webset status until complete or timeout."""
        from api.services import get_exa_client

        client = get_exa_client()
        task = self._tasks.get(webset_id)

        if not task:
            return

        task.status = "polling"

        for _ in range(max_polls):
            await asyncio.sleep(interval)

            status = await client.get_webset_status(webset_id)
            if not status:
                task.status = "failed"
                logger.warning("Failed to get Webset status: %s", webset_id)
                return

            if status.status == "idle":
                # Webset complete - fetch results
                task.status = "complete"
                events = await client.get_webset_items(webset_id)

                logger.info("Webset %s complete with %s events", webset_id, len(events))

                # Call completion callback if registered
                callback = self._callbacks.get(webset_id)
                if callback:
                    try:
                        await callback(task.session_id, events)
                    except Exception as e:
                        logger.error("Webset callback error: %s", e)

                return

        # Timeout
        task.status = "timeout"
        logger.warning("Webset %s polling timeout", webset_id)

    def get_task_status(self, webset_id: str) -> WebsetTask | None:
        """Get status of a background task."""
        return self._tasks.get(webset_id)


# Singleton
_manager: BackgroundTaskManager | None = None


def get_background_task_manager() -> BackgroundTaskManager:
    """Get the singleton background task manager."""
    global _manager
    if _manager is None:
        _manager = BackgroundTaskManager()
    return _manager
```

#### 4.2 SSE Connection Manager for Updates

**File**: `api/services/sse_connections.py` (new file)
**Changes**: Track active SSE connections for sending updates

```python
"""
SSE connection manager for sending updates to connected clients.
"""

import asyncio
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """Manages active SSE connections by session ID."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    def register(self, session_id: str) -> asyncio.Queue:
        """Register a session and return its message queue."""
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    def unregister(self, session_id: str) -> None:
        """Unregister a session."""
        self._queues.pop(session_id, None)

    async def send_update(self, session_id: str, event_type: str, data: dict) -> bool:
        """Send an update to a connected session. Returns True if sent."""
        queue = self._queues.get(session_id)
        if queue:
            await queue.put({"type": event_type, **data})
            return True
        return False


# Singleton
_manager: SSEConnectionManager | None = None


def get_sse_manager() -> SSEConnectionManager:
    """Get the singleton SSE connection manager."""
    global _manager
    if _manager is None:
        _manager = SSEConnectionManager()
    return _manager
```

#### 4.3 Integrate Websets into Search Flow

**File**: `api/agents/search.py`
**Changes**: Start Websets after instant results

```python
from api.services.background_tasks import get_background_task_manager
from api.services.event_cache import get_event_cache


async def _start_deep_discovery(
    profile: SearchProfile,
    session_id: str | None,
) -> str | None:
    """Start Websets deep discovery in background."""
    if not session_id:
        return None

    settings = get_settings()
    if not settings.exa_api_key:
        return None

    client = get_exa_client()

    # Build query
    query_parts = profile.categories or ["events"]
    if profile.keywords:
        query_parts.extend(profile.keywords)
    query = " ".join(query_parts)
    location = "Columbus, OH"

    # Create Webset
    webset_id = await client.create_webset(query, location, count=20)
    if not webset_id:
        return None

    # Start background polling
    manager = get_background_task_manager()
    manager.start_webset_task(
        webset_id=webset_id,
        session_id=session_id,
        query=query,
        location=location,
        on_complete=_on_webset_complete,
    )

    return webset_id


async def _on_webset_complete(session_id: str, events: list) -> None:
    """Handle Websets completion - cache results and notify user."""
    from api.services.sse_connections import get_sse_manager
    from api.services.event_cache import get_event_cache

    if not events:
        return

    cache = get_event_cache()
    sse_manager = get_sse_manager()

    # Convert to EventResult format
    event_results = []
    for event in events:
        venue = event.venue_name or "TBD"
        if event.venue_address:
            venue = f"{venue}, {event.venue_address}"

        event_results.append({
            "id": f"webset_{event.id}",
            "title": event.title,
            "date": event.start_time.isoformat() if event.start_time else "",
            "location": venue,
            "category": "community",
            "description": event.description[:200] if event.description else "",
            "is_free": event.is_free if event.is_free is not None else True,
            "price_amount": event.price_amount,
            "url": event.url,
            "image_url": event.image_url,
            "source": "exa_websets",
        })

    # Cache the results
    cache.cache_events(event_results, [], "Columbus, OH", None)

    # Send SSE update to connected client
    await sse_manager.send_update(
        session_id,
        "more_events",
        {
            "events": [
                {
                    "id": e["id"],
                    "title": e["title"],
                    "startTime": e["date"],
                    "location": e["location"],
                    "categories": [e["category"]],
                    "url": e["url"],
                    "imageUrl": e["image_url"],
                    "source": e["source"],
                }
                for e in event_results
            ],
            "message": f"Found {len(event_results)} more events!",
        },
    )
```

#### 4.4 Update Streaming Endpoint

**File**: `api/index.py`
**Changes**: Start deep discovery and handle SSE updates

```python
from api.services.sse_connections import get_sse_manager
from api.agents.search import _start_deep_discovery


async def stream_chat_response(
    message: str,
    session: SQLiteSession | None = None,
    session_id: str | None = None,  # NEW parameter
) -> AsyncGenerator[str, None]:
    """Stream chat response with deep discovery support."""

    # Register for SSE updates if session provided
    sse_manager = get_sse_manager()
    update_queue = None
    if session_id:
        update_queue = sse_manager.register(session_id)

    try:
        # ... existing clarifying agent code ...

        if output.ready_to_search and output.search_profile:
            # ... existing search code ...

            # Start deep discovery in background
            if session_id and search_result.events:
                webset_id = await _start_deep_discovery(
                    output.search_profile,
                    session_id,
                )
                if webset_id:
                    logger.info("Started Websets deep discovery: %s", webset_id)

            # ... rest of existing code ...

        yield sse_event("done", {})

        # Keep connection open for updates (with timeout)
        if update_queue:
            try:
                while True:
                    update = await asyncio.wait_for(update_queue.get(), timeout=300)
                    yield sse_event(update["type"], update)
            except asyncio.TimeoutError:
                pass

    finally:
        if session_id:
            sse_manager.unregister(session_id)
```

### Success Criteria:

#### Automated Verification:
- [ ] Unit tests pass: `pytest api/services/tests/test_background_tasks.py -v`
- [ ] Type checking passes for all new files

#### Manual Verification:
- [ ] Search returns instant results from Eventbrite/Exa Search
- [ ] Logs show "Started Websets deep discovery"
- [ ] After delay, frontend receives "more_events" SSE event
- [ ] New events cached and appear in subsequent searches

**Implementation Note**: After completing this phase, proceed to Phase 5.

---

## Phase 5: Testing & Documentation

### Overview
Add comprehensive tests and update documentation.

### Changes Required:

#### 5.1 Exa Client Tests

**File**: `api/services/tests/test_exa_client.py` (new file)

```python
"""Tests for Exa API client."""

import os
import pytest
from unittest.mock import patch, AsyncMock

from api.services.exa_client import ExaClient, get_exa_client


class TestExaClient:
    """Test ExaClient class."""

    def test_no_api_key_returns_empty(self):
        """Without API key, search returns empty results."""
        with patch.dict(os.environ, {}, clear=True):
            client = ExaClient(api_key="")
            # Note: Would need to run async
            # result = await client.search_events("test")
            # assert result.events == []

    @pytest.mark.asyncio
    async def test_search_events_with_mock(self):
        """Test search with mocked HTTP response."""
        client = ExaClient(api_key="test_key")

        mock_response = {
            "results": [
                {
                    "id": "123",
                    "title": "Test Event",
                    "url": "https://example.com/event",
                    "summary": '{"name": "Test Event", "date": "2026-01-15"}',
                }
            ]
        }

        with patch.object(client, "_get_search_client") as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value.json.return_value = mock_response
            mock_http.post.return_value.raise_for_status = lambda: None
            mock_client.return_value = mock_http

            result = await client.search_events("tech events")

            assert len(result.events) == 1
            assert result.events[0].title == "Test Event"


class TestGetExaClient:
    """Test singleton client getter."""

    def test_returns_singleton(self):
        """Should return same instance."""
        client1 = get_exa_client()
        client2 = get_exa_client()
        assert client1 is client2
```

#### 5.2 Event Cache Tests

**File**: `api/services/tests/test_event_cache.py` (new file)

```python
"""Tests for event cache."""

import tempfile
import pytest
from datetime import datetime

from api.services.event_cache import EventCache


class TestEventCache:
    """Test EventCache class."""

    @pytest.fixture
    def cache(self):
        """Create cache with temp database."""
        with tempfile.NamedTemporaryFile(suffix=".db") as f:
            return EventCache(db_path=f.name, ttl_hours=1)

    def test_cache_and_retrieve(self, cache):
        """Test caching and retrieving events."""
        events = [
            {
                "id": "1",
                "title": "Test Event",
                "date": "2026-01-15",
                "location": "Columbus, OH",
                "category": "tech",
                "description": "A test event",
                "is_free": True,
                "source": "test",
            }
        ]

        cache.cache_events(events, ["tech"], "Columbus, OH", None)

        cached = cache.get_cached_events(["tech"], "Columbus, OH", None)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].title == "Test Event"

    def test_cache_miss_different_query(self, cache):
        """Different query should miss cache."""
        events = [{"id": "1", "title": "Test", "source": "test"}]
        cache.cache_events(events, ["tech"], "Columbus, OH", None)

        cached = cache.get_cached_events(["music"], "Columbus, OH", None)
        assert cached is None
```

#### 5.3 Update Environment Example

**File**: `.env.example`
**Changes**: Add Exa API key

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Event Sources
EVENTBRITE_API_KEY=your_eventbrite_key
EXA_API_KEY=your_exa_api_key

# Server
CORS_ORIGINS=http://localhost:3000

# Observability (optional)
HYPERDX_API_KEY=
```

#### 5.4 Update Requirements

**File**: `requirements.txt`
**Changes**: Add python-dateutil for date parsing

```
# Add to existing requirements
python-dateutil>=2.8.2
```

### Success Criteria:

#### Automated Verification:
- [ ] All tests pass: `pytest api/ -v`
- [ ] No type errors: `cd api && python -m mypy .`
- [ ] Linting passes: `ruff check api/`

#### Manual Verification:
- [ ] `.env.example` documents all required keys
- [ ] Server starts without Exa key (graceful degradation)
- [ ] Full flow works with all keys configured

---

## Testing Strategy

### Unit Tests:
- ExaClient: search, webset creation, parsing
- EventCache: CRUD operations, TTL expiration
- Deduplication: URL matching, title normalization
- Background tasks: polling, callbacks

### Integration Tests:
- Multi-source search with both APIs
- Cache integration with search
- SSE update delivery

### Manual Testing Steps:
1. Start server with only `EVENTBRITE_API_KEY` - verify Eventbrite-only results
2. Add `EXA_API_KEY` - verify both sources return events
3. Run same search twice - verify second is cache hit
4. Wait for Websets completion - verify "more_events" arrives
5. Verify deduplication with overlapping events

## Performance Considerations

1. **Parallel API Calls**: Eventbrite and Exa Search run concurrently via `asyncio.gather()`
2. **Cache TTL**: 24-hour default balances freshness with API cost reduction
3. **Websets Polling**: 30-second intervals to avoid rate limiting
4. **SSE Connection Timeout**: 5-minute keepalive prevents zombie connections

## Migration Notes

- No database migrations needed (SQLite creates tables on first run)
- Existing Eventbrite-only deployments continue working
- New `EXA_API_KEY` optional - graceful degradation if missing
- Cache database (`event_cache.db`) auto-created in `api/` directory

## References

- Research document: `throughts/research/2026-01-10-exa-websets-event-search-research.md`
- Eventbrite client pattern: `api/services/eventbrite.py:35-57`
- Search function: `api/agents/search.py:124-166`
- SSE streaming: `api/index.py:104-197`
- Exa Websets docs: https://docs.exa.ai/websets/overview
- Exa Search API: https://exa.ai/docs/reference/search
