# Meetup GraphQL API Integration Plan

## Overview

This plan implements the Meetup GraphQL API as a new event source for Calendar Club using the `gql` Python library. The implementation follows the Registry Pattern architecture established in `throughts/shared/plans/2026-01-11-event-source-registry-pattern.md`.

**CRITICAL DEPENDENCY**: This plan **requires** the Event Source Registry Pattern (Plan `2026-01-11-event-source-registry-pattern.md`) to be implemented first. The registry pattern must be complete before beginning Phase 2 of this plan. Phase 1 (dependency installation) can proceed independently.

## Current State Analysis

### What Exists Now

The codebase has two active event source clients:

1. **EventbriteClient** (`api/services/eventbrite.py:46-398`)
   - Async client using `httpx`
   - Constructor: `__init__(api_key: str | None = None)` with env fallback
   - Search: `search_events(location, start_date, end_date, ...) -> list[EventbriteEvent]`
   - Singleton: `get_eventbrite_client()`

2. **ExaClient** (`api/services/exa_client.py:41-306`)
   - Async client using `httpx`
   - Constructor: `__init__(api_key: str | None = None)` with env fallback
   - Search: `search(query, num_results, ...) -> list[ExaSearchResult]`
   - Singleton: `get_exa_client()`

### Current Integration Point

`api/agents/search.py:334-349` has hardcoded source checking:
```python
has_eventbrite = bool(settings.eventbrite_api_key)  # Line 335
has_exa = bool(settings.exa_api_key)                # Line 336
```

**After registry implementation**, this becomes:
```python
registry = get_registry()
available_sources = registry.get_available(settings)
```

### Key Discoveries

- The `gql` library is not currently installed (checked `pyproject.toml`)
- Meetup requires OAuth 2.0 authentication (Bearer token)
- Meetup requires lat/lon coordinates, not city names (geocoding needed)
- GraphQL endpoint: `https://api.meetup.com/gql`
- Rate limit: 500 points per 60 seconds

## Desired End State

After implementation:

1. **MeetupClient** exists at `api/services/meetup.py` following the established pattern
2. **`gql[aiohttp]`** dependency is installed
3. **Settings** includes `meetup_client_id`, `meetup_client_secret`, and `meetup_access_token`
4. **Meetup is registered** as an event source in the registry
5. **No changes to `search_events()`** - registry handles discovery automatically

### Verification

- `pytest api/services/tests/test_meetup.py` passes
- `pytest api/agents/tests/test_search.py` passes
- `ruff check api/` passes
- `mypy api/services/meetup.py` passes
- Manual test: Search returns Meetup events when API key is configured

## What We're NOT Doing

- NOT implementing OAuth 2.0 token refresh flow (assumes pre-configured token)
- NOT implementing geocoding service (assumes lat/lon in profile or uses Columbus defaults)
- NOT handling rate limiting (first iteration; can add later)
- NOT implementing WebSocket subscriptions for real-time updates
- NOT adding new fields to EventResult model

## Implementation Approach

This plan has a **blocking dependency** on the registry pattern:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEPENDENCY CHAIN                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Event Source Registry Pattern (2026-01-11)                          │   │
│   │  - Creates base.py with EventSource, EventSourceRegistry             │   │
│   │  - Migrates Eventbrite and Exa to registry                           │   │
│   │  - Updates search_events() to use registry                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              │ BLOCKS (must complete first)                  │
│                              ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Meetup GraphQL Integration (This Plan)                              │   │
│   │  - Phase 1: Add gql dependency (can start independently)             │   │
│   │  - Phase 2+: Requires registry (blocked until registry complete)     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why registry first?**
- Without the registry, adding Meetup requires modifying `search_events()` directly
- This would add more hardcoded conditionals (anti-pattern)
- Registry enables "add source, no changes to orchestrator" pattern

## Phase 1: Add gql Dependency

### Overview
Install the `gql` GraphQL library with aiohttp transport.

**Note**: This phase can proceed independently of the registry pattern.

### Changes Required:

#### 1.1 Update pyproject.toml

**File**: `pyproject.toml`
**Changes**: Add gql dependency

```toml
# Add to dependencies list (after httpx line):
    "gql[aiohttp]>=3.5.0",
```

#### 1.2 Install Dependency

**Command**: Run `uv sync` or `pip install gql[aiohttp]`

### Success Criteria:

#### Automated Verification:
- [ ] Import works: `python -c "from gql import gql, Client; from gql.transport.aiohttp import AIOHTTPTransport; print('OK')"`
- [ ] No dependency conflicts: `uv sync` succeeds

#### Manual Verification:
- [ ] Verify gql version >= 3.5.0 installed

**Implementation Note**: After completing this phase, proceed to Phase 2 only if the Registry Pattern plan is complete.

---

## Phase 2: Create Meetup Client

### Overview
Create the MeetupClient following the established pattern from EventbriteClient and ExaClient.

**BLOCKER**: This phase requires the Event Source Registry Pattern to be implemented first. Verify by checking that `api/services/base.py` exists with `EventSource` and `register_source`.

### Changes Required:

#### 2.1 Create MeetupEvent Model and Client

**File**: `api/services/meetup.py` (NEW FILE)
**Changes**: Create complete client module

```python
"""
Meetup GraphQL API client for event discovery.

Provides async methods to search events from Meetup using their GraphQL API.

NOTE: Meetup Pro subscription is required for API access.
See: https://www.meetup.com/api/guide/
"""

import logging
import os
from datetime import datetime
from typing import Any

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MeetupEvent(BaseModel):
    """Parsed event from Meetup GraphQL API."""

    id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: int | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    venue_lat: float | None = None
    venue_lon: float | None = None
    group_name: str | None = None
    group_urlname: str | None = None
    category: str = "community"
    is_free: bool = True
    url: str | None = None
    image_url: str | None = None


class MeetupClient:
    """Async client for Meetup GraphQL API.

    Requires OAuth 2.0 access token. Meetup Pro subscription required.
    """

    GRAPHQL_ENDPOINT = "https://api.meetup.com/gql"

    # GraphQL query for searching events by location
    SEARCH_EVENTS_QUERY = gql("""
        query SearchEvents($lat: Float!, $lon: Float!, $radius: Int, $first: Int) {
            rankedEvents(filter: {lat: $lat, lon: $lon, radius: $radius}, first: $first) {
                count
                edges {
                    node {
                        id
                        title
                        description
                        dateTime
                        duration
                        eventUrl
                        venue {
                            name
                            address
                            lat
                            lon
                        }
                        group {
                            name
                            urlname
                        }
                        featuredEventPhoto {
                            baseUrl
                        }
                        feeSettings {
                            amount
                            currency
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    """)

    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        """Initialize Meetup client.

        Args:
            access_token: OAuth 2.0 access token (or MEETUP_ACCESS_TOKEN env var)
            client_id: OAuth client ID (for future token refresh)
            client_secret: OAuth client secret (for future token refresh)
        """
        self.access_token = access_token or os.getenv("MEETUP_ACCESS_TOKEN")
        self.client_id = client_id or os.getenv("MEETUP_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("MEETUP_CLIENT_SECRET")
        self._client: Client | None = None
        self._transport: AIOHTTPTransport | None = None

    async def _get_client(self) -> Client:
        """Get or create the GraphQL client."""
        if self._client is None:
            if not self.access_token:
                raise ValueError("MEETUP_ACCESS_TOKEN not configured")

            self._transport = AIOHTTPTransport(
                url=self.GRAPHQL_ENDPOINT,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            self._client = Client(
                transport=self._transport,
                fetch_schema_from_transport=False,  # Don't fetch schema for speed
            )
        return self._client

    async def close(self) -> None:
        """Close the GraphQL client."""
        if self._transport:
            await self._transport.close()
            self._transport = None
        self._client = None

    async def search_events(
        self,
        latitude: float,
        longitude: float,
        radius_miles: int = 25,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 10,
    ) -> list[MeetupEvent]:
        """
        Search for events on Meetup using their GraphQL API.

        Args:
            latitude: Search center latitude
            longitude: Search center longitude
            radius_miles: Search radius in miles
            start_date: Filter events starting after this date (not supported by rankedEvents)
            end_date: Filter events ending before this date (not supported by rankedEvents)
            limit: Maximum number of results

        Returns:
            List of MeetupEvent objects

        Note:
            The rankedEvents query returns events ranked by relevance/proximity.
            Date filtering is not directly supported; client-side filtering may be needed.
        """
        if not self.access_token:
            logger.warning("MEETUP_ACCESS_TOKEN not set, returning empty results")
            return []

        try:
            client = await self._get_client()

            # Convert miles to meters (Meetup API uses meters for radius)
            radius_meters = int(radius_miles * 1609.34)

            variables = {
                "lat": latitude,
                "lon": longitude,
                "radius": radius_meters,
                "first": limit,
            }

            async with client as session:
                result = await session.execute(
                    self.SEARCH_EVENTS_QUERY,
                    variable_values=variables,
                )

            events = []
            ranked_events = result.get("rankedEvents", {})

            for edge in ranked_events.get("edges", []):
                event = self._parse_event(edge.get("node", {}))
                if event:
                    # Client-side date filtering if needed
                    if start_date and event.start_time < start_date:
                        continue
                    if end_date and event.start_time > end_date:
                        continue
                    events.append(event)

            logger.info("Meetup API returned %d events", len(events))
            return events

        except Exception as e:
            logger.warning("Meetup GraphQL API error: %s", e)
            return []

    def _parse_event(self, data: dict[str, Any]) -> MeetupEvent | None:
        """Parse GraphQL response into MeetupEvent."""
        try:
            # Parse datetime
            date_str = data.get("dateTime")
            if not date_str:
                return None
            start_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

            # Calculate end time from duration (in milliseconds)
            duration_ms = data.get("duration")
            end_time = None
            if duration_ms:
                from datetime import timedelta
                end_time = start_time + timedelta(milliseconds=duration_ms)

            # Parse venue
            venue = data.get("venue") or {}
            venue_name = venue.get("name")
            venue_address = venue.get("address")
            venue_lat = venue.get("lat")
            venue_lon = venue.get("lon")

            # Parse group
            group = data.get("group") or {}
            group_name = group.get("name")
            group_urlname = group.get("urlname")

            # Parse image
            image_url = None
            photo = data.get("featuredEventPhoto")
            if photo:
                image_url = photo.get("baseUrl")

            # Parse fee (if present, event is paid)
            is_free = True
            fee_settings = data.get("feeSettings")
            if fee_settings and fee_settings.get("amount"):
                is_free = fee_settings["amount"] == 0

            return MeetupEvent(
                id=data.get("id", ""),
                title=data.get("title", "Untitled Event"),
                description=data.get("description", "")[:500],
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                venue_name=venue_name,
                venue_address=venue_address,
                venue_lat=venue_lat,
                venue_lon=venue_lon,
                group_name=group_name,
                group_urlname=group_urlname,
                category="community",  # Meetup doesn't expose category in this query
                is_free=is_free,
                url=data.get("eventUrl"),
                image_url=image_url,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Error parsing Meetup event: %s", e)
            return None


# Singleton instance
_client: MeetupClient | None = None


def get_meetup_client() -> MeetupClient:
    """Get the singleton Meetup client."""
    global _client
    if _client is None:
        _client = MeetupClient()
    return _client
```

### Success Criteria:

#### Automated Verification:
- [ ] File exists: `api/services/meetup.py`
- [ ] Type checking passes: `mypy api/services/meetup.py`
- [ ] Linting passes: `ruff check api/services/meetup.py`
- [ ] Import works: `python -c "from api.services.meetup import MeetupClient, MeetupEvent, get_meetup_client; print('OK')"`

#### Manual Verification:
- [ ] Code structure matches EventbriteClient pattern

**Implementation Note**: After completing this phase and automated verification passes, proceed to Phase 3.

---

## Phase 3: Add Meetup Configuration

### Overview
Add Meetup OAuth credentials to the Settings model.

### Changes Required:

#### 3.1 Update Settings Model

**File**: `api/config.py`
**Changes**: Add Meetup configuration fields

Add after line 21 (after `firecrawl_api_key`):
```python
    # Meetup OAuth (requires Pro subscription)
    meetup_client_id: str = Field(default="", description="Meetup OAuth client ID")
    meetup_client_secret: str = Field(default="", description="Meetup OAuth client secret")
    meetup_access_token: str = Field(default="", description="Meetup OAuth access token")
```

#### 3.2 Update has_event_source Property

**File**: `api/config.py`
**Changes**: Include meetup in source check

Replace lines 51-53:
```python
    @property
    def has_event_source(self) -> bool:
        """Check if any event source is configured."""
        return (
            bool(self.eventbrite_api_key)
            or bool(self.exa_api_key)
            or bool(self.meetup_access_token)
        )
```

#### 3.3 Update .env.example

**File**: `.env.example`
**Changes**: Add Meetup environment variables

Add to the file:
```bash
# Meetup OAuth (requires Meetup Pro subscription)
# See: https://www.meetup.com/api/guide/
MEETUP_CLIENT_ID=
MEETUP_CLIENT_SECRET=
MEETUP_ACCESS_TOKEN=
```

### Success Criteria:

#### Automated Verification:
- [ ] Import works: `python -c "from api.config import Settings; s = Settings(); print(s.meetup_access_token)"`
- [ ] Type checking passes: `mypy api/config.py`
- [ ] Linting passes: `ruff check api/config.py`

#### Manual Verification:
- [ ] `.env.example` includes Meetup variables

**Implementation Note**: After completing this phase and automated verification passes, proceed to Phase 4.

---

## Phase 4: Add Meetup Fetcher and Register Source

### Overview
Create the fetcher function in search.py and register Meetup as an event source.

**BLOCKER**: This phase requires the Event Source Registry Pattern to be fully implemented. Verify:
1. `api/services/base.py` exists with `EventSource` and `register_source`
2. `api/agents/search.py` uses `get_registry()` instead of hardcoded source checks

### Changes Required:

#### 4.1 Add Meetup Fetcher to search.py

**File**: `api/agents/search.py`
**Changes**: Add fetcher function

Add import at top (with other service imports):
```python
from api.services.meetup import get_meetup_client
```

Add after `_fetch_exa_events` function (around line 212):
```python
# Columbus, OH coordinates for default location
COLUMBUS_LAT = 39.9612
COLUMBUS_LON = -82.9988


async def _fetch_meetup_events(profile: SearchProfile) -> list[EventResult]:
    """Fetch events from Meetup GraphQL API."""
    client = get_meetup_client()

    # Use Columbus, OH as default location
    # TODO: Add geocoding support for profile.location
    latitude = COLUMBUS_LAT
    longitude = COLUMBUS_LON

    # Parse time window
    start_date: datetime | None = None
    end_date: datetime | None = None
    if profile.time_window:
        start_value = profile.time_window.start
        end_value = profile.time_window.end
        if isinstance(start_value, str):
            start_date = datetime.fromisoformat(start_value)
        else:
            start_date = start_value
        if isinstance(end_value, str):
            end_date = datetime.fromisoformat(end_value)
        else:
            end_date = end_value

    try:
        events = await client.search_events(
            latitude=latitude,
            longitude=longitude,
            radius_miles=25,
            start_date=start_date,
            end_date=end_date,
            limit=10,
        )

        results = []
        for event in events:
            # Build venue string
            venue = event.venue_name or "TBD"
            if event.venue_address:
                venue = f"{venue}, {event.venue_address}"

            # Add group name to description for context
            description = event.description[:200] if event.description else ""
            if event.group_name:
                description = f"Hosted by {event.group_name}. {description}"

            results.append(
                EventResult(
                    id=f"meetup-{event.id}",
                    title=event.title,
                    date=event.start_time.isoformat(),
                    location=venue,
                    category=event.category,
                    description=description[:200],  # Ensure truncation
                    is_free=event.is_free,
                    price_amount=None,  # Meetup doesn't provide price amount
                    distance_miles=5.0,  # Default; could calculate from venue_lat/lon
                    url=event.url,
                )
            )

        return results

    except Exception as e:
        logger.warning("Meetup fetch error: %s", e)
        return []
```

#### 4.2 Register Meetup Source

**File**: `api/services/meetup.py`
**Changes**: Add source registration at end of file

Add import at top:
```python
from api.services.base import EventSource, register_source
```

Add at end of file (before the last blank line):
```python


def _create_meetup_source() -> None:
    """Register Meetup as an event source.

    Note: The fetcher is imported lazily to avoid circular imports.
    """
    from api.agents.search import _fetch_meetup_events

    register_source(
        EventSource(
            name="meetup",
            fetcher=_fetch_meetup_events,
            config_key="meetup_access_token",
            description="Meetup GraphQL API for community events",
        )
    )


# Register on module import
_create_meetup_source()
```

#### 4.3 Import Meetup Module in Search

**File**: `api/agents/search.py`
**Changes**: Ensure Meetup module is imported to trigger registration

Add with other source module imports (should be near top, with eventbrite and exa imports):
```python
# Import to ensure sources are registered
import api.services.meetup  # noqa: F401
```

### Success Criteria:

#### Automated Verification:
- [ ] Import works: `python -c "from api.agents.search import _fetch_meetup_events; print('OK')"`
- [ ] Source registered: `python -c "from api.services import get_registry; import api.services.meetup; print([s.name for s in get_registry().all_sources()])"`
- [ ] Shows meetup in list: output should include `meetup`
- [ ] Type checking passes: `mypy api/agents/search.py`
- [ ] Linting passes: `ruff check api/`

#### Manual Verification:
- [ ] Verify no circular import errors occur

**Implementation Note**: After completing this phase and all automated verification passes, proceed to Phase 5.

---

## Phase 5: Export from Services Package

### Overview
Export the new Meetup client from the services package.

### Changes Required:

#### 5.1 Update Services __init__.py

**File**: `api/services/__init__.py`
**Changes**: Add Meetup exports

Add import after line 22 (after firecrawl imports):
```python
from .meetup import MeetupClient, MeetupEvent, get_meetup_client
```

Add to `__all__` list (after firecrawl exports):
```python
    "MeetupClient",
    "MeetupEvent",
    "get_meetup_client",
```

### Success Criteria:

#### Automated Verification:
- [ ] Import works: `python -c "from api.services import MeetupClient, MeetupEvent, get_meetup_client; print('OK')"`
- [ ] Linting passes: `ruff check api/services/__init__.py`

#### Manual Verification:
- [ ] Verify exports are alphabetically ordered in `__all__`

---

## Phase 6: Add Meetup Client Tests

### Overview
Add comprehensive tests for the MeetupClient.

### Changes Required:

#### 6.1 Create Test File

**File**: `api/services/tests/test_meetup.py` (NEW FILE)
**Changes**: Add unit tests

```python
"""Tests for Meetup GraphQL client."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.meetup import MeetupClient, MeetupEvent, get_meetup_client

if TYPE_CHECKING:
    pass


class TestMeetupEvent:
    """Tests for MeetupEvent model."""

    def test_meetup_event_creation(self) -> None:
        """Test creating a MeetupEvent."""
        event = MeetupEvent(
            id="123",
            title="Test Meetup",
            description="A test event",
            start_time=datetime(2026, 1, 15, 18, 0),
            venue_name="Test Venue",
            venue_address="123 Main St",
            group_name="Test Group",
            is_free=True,
            url="https://meetup.com/test-group/events/123",
        )

        assert event.id == "123"
        assert event.title == "Test Meetup"
        assert event.is_free is True
        assert event.category == "community"  # Default

    def test_meetup_event_optional_fields(self) -> None:
        """Test MeetupEvent with minimal fields."""
        event = MeetupEvent(
            id="456",
            title="Minimal Event",
            description="",
            start_time=datetime(2026, 1, 20, 19, 0),
        )

        assert event.venue_name is None
        assert event.group_name is None
        assert event.end_time is None


class TestMeetupClient:
    """Tests for MeetupClient class."""

    def test_init_with_env_fallback(self) -> None:
        """Test client initializes with environment variable fallback."""
        with patch.dict("os.environ", {"MEETUP_ACCESS_TOKEN": "test-token"}):
            client = MeetupClient()
            assert client.access_token == "test-token"

    def test_init_with_explicit_token(self) -> None:
        """Test client initializes with explicit token."""
        client = MeetupClient(access_token="explicit-token")
        assert client.access_token == "explicit-token"

    @pytest.mark.asyncio
    async def test_search_events_no_token(self) -> None:
        """Test search returns empty list when no token configured."""
        client = MeetupClient(access_token="")
        results = await client.search_events(
            latitude=39.96,
            longitude=-83.00,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_search_events_success(self) -> None:
        """Test successful event search."""
        client = MeetupClient(access_token="test-token")

        # Mock the GraphQL response
        mock_result = {
            "rankedEvents": {
                "edges": [
                    {
                        "node": {
                            "id": "event-123",
                            "title": "Columbus Tech Meetup",
                            "description": "Monthly tech gathering",
                            "dateTime": "2026-01-15T18:00:00Z",
                            "duration": 7200000,  # 2 hours in ms
                            "eventUrl": "https://meetup.com/test/events/123",
                            "venue": {
                                "name": "Tech Hub",
                                "address": "123 Innovation Way",
                                "lat": 39.96,
                                "lon": -83.00,
                            },
                            "group": {
                                "name": "Columbus Techies",
                                "urlname": "columbus-techies",
                            },
                            "featuredEventPhoto": {
                                "baseUrl": "https://meetup.com/photos/123.jpg",
                            },
                            "feeSettings": None,
                        }
                    }
                ]
            }
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=mock_result)

            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_session)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_get_client.return_value = mock_client

            results = await client.search_events(
                latitude=39.96,
                longitude=-83.00,
                limit=10,
            )

        assert len(results) == 1
        assert results[0].id == "event-123"
        assert results[0].title == "Columbus Tech Meetup"
        assert results[0].is_free is True
        assert results[0].venue_name == "Tech Hub"

    def test_parse_event_missing_datetime(self) -> None:
        """Test _parse_event returns None for missing datetime."""
        client = MeetupClient(access_token="test")
        result = client._parse_event({"id": "123", "title": "Test"})
        assert result is None

    def test_parse_event_success(self) -> None:
        """Test _parse_event with valid data."""
        client = MeetupClient(access_token="test")
        data = {
            "id": "123",
            "title": "Test Event",
            "description": "A description",
            "dateTime": "2026-01-15T18:00:00Z",
            "duration": 3600000,
            "eventUrl": "https://meetup.com/test",
            "venue": {
                "name": "Test Venue",
                "address": "123 Test St",
            },
            "group": {
                "name": "Test Group",
            },
            "feeSettings": {
                "amount": 10,
                "currency": "USD",
            },
        }

        result = client._parse_event(data)

        assert result is not None
        assert result.id == "123"
        assert result.title == "Test Event"
        assert result.is_free is False  # Has fee
        assert result.venue_name == "Test Venue"


class TestGlobalClient:
    """Tests for singleton client."""

    def test_get_meetup_client_singleton(self) -> None:
        """Test that get_meetup_client returns same instance."""
        # Reset singleton
        import api.services.meetup as meetup_module
        meetup_module._client = None

        client1 = get_meetup_client()
        client2 = get_meetup_client()

        assert client1 is client2


class TestMeetupRegistration:
    """Tests for event source registration."""

    def test_meetup_registered_as_source(self) -> None:
        """Test that Meetup is registered in the event source registry."""
        from api.services import get_registry

        # Import to trigger registration
        import api.services.meetup  # noqa: F401

        registry = get_registry()
        source_names = [s.name for s in registry.all_sources()]

        assert "meetup" in source_names

    def test_meetup_source_has_correct_config_key(self) -> None:
        """Test that Meetup source uses correct config key."""
        from api.services import get_registry

        import api.services.meetup  # noqa: F401

        registry = get_registry()
        meetup_source = registry.get("meetup")

        assert meetup_source is not None
        assert meetup_source.config_key == "meetup_access_token"
```

### Success Criteria:

#### Automated Verification:
- [ ] Tests pass: `pytest api/services/tests/test_meetup.py -v`
- [ ] Linting passes: `ruff check api/services/tests/test_meetup.py`

#### Manual Verification:
- [ ] Review test coverage is adequate

---

## Testing Strategy

### Unit Tests:
- MeetupClient initialization
- GraphQL response parsing
- Error handling (no token, API errors)
- Event model creation

### Integration Tests:
- Source registration verification
- Search flow with Meetup enabled

### Manual Testing Steps:
1. Configure `MEETUP_ACCESS_TOKEN` in `.env`
2. Run the API server
3. Execute a search request
4. Verify Meetup events appear in results
5. Verify source attribution includes "meetup"
6. Test with token missing (should gracefully skip)

## Performance Considerations

- GraphQL query is minimal (no schema fetch)
- Client-side date filtering may return fewer results than requested
- Consider adding request caching for repeated queries
- Rate limit (500 points/60s) not currently enforced

## Migration Notes

- No database migrations required
- Existing searches continue to work
- Meetup only activates when token is configured
- No breaking changes to API responses

## Future Enhancements

1. **OAuth Token Refresh**: Implement automatic token refresh using client_id/secret
2. **Geocoding**: Add geocoding service to convert city names to lat/lon
3. **Rate Limiting**: Add request queuing to respect 500 points/60s limit
4. **Category Mapping**: Map Meetup topics to our category system
5. **Pagination**: Support fetching more than initial page

## References

- Original research: `throughts/shared/research/2026-01-11-meetup-graphql-integration.md`
- Registry pattern plan: `throughts/shared/plans/2026-01-11-event-source-registry-pattern.md`
- Meetup API docs: https://www.meetup.com/api/guide/
- Meetup GraphQL playground: https://www.meetup.com/api/playground/
- gql library: https://github.com/graphql-python/gql
- EventbriteClient pattern: `api/services/eventbrite.py:46-398`
- ExaClient pattern: `api/services/exa_client.py:41-306`
