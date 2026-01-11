# FireCrawl/Posh Event Source Integration Plan

## Overview

Integrate FireCrawl/Posh as an event source in the registry pattern and wire up all event source registrations at app startup. This fixes the core issue where no event sources are registered (causing searches to return empty) while also adding Posh as a third event source.

## Current State Analysis

### What Exists:
- `PoshExtractor` class with `discover_events(city, limit)` method (`firecrawl.py:152-347`)
- `ScrapedEvent` model compatible with other event types (`firecrawl.py:24-41`)
- Registration functions exist but are never called:
  - `register_eventbrite_source()` at `eventbrite.py:472-486`
  - `register_exa_source()` at `exa_client.py:408-421`

### What's Missing:
- `search_events_adapter()` for Posh/FireCrawl
- `register_posh_source()` function
- `_convert_scraped_event()` in search.py
- Registration calls at app startup

### Key Discoveries:
- All adapters use duck-typed `profile: Any` parameter (`eventbrite.py:428`, `exa_client.py:353`)
- Location is hardcoded to "Columbus, OH" in existing adapters (`eventbrite.py:441`, `exa_client.py:366`)
- Conversion functions exist for each source type (`search.py:75-123`)
- Eventbrite priority=10, Exa priority=20

## Desired End State

After implementation:
1. All three event sources (Eventbrite, Exa, Posh) are registered at app startup
2. `search_events()` queries all enabled sources in parallel
3. Posh events are filtered by time_window and free_only from SearchProfile
4. Debug logs show all three sources being queried

### Verification:
```bash
LOG_LEVEL=DEBUG uv run uvicorn api.index:app --reload
# Should see on startup:
# INFO - Registered event source: eventbrite
# INFO - Registered event source: exa
# INFO - Registered event source: posh

# On search, should see:
# 🔍 [Search] Starting parallel fetch | sources=eventbrite, exa, posh
```

## What We're NOT Doing

- Adding location field to SearchProfile (future refactor - hardcode "columbus" for now)
- Category filtering for Posh (all Posh events are "nightlife")
- Keyword filtering for Posh (discover_events doesn't support it)
- Modifying the PoshExtractor.discover_events() method itself

## Implementation Approach

Create the adapter following the established pattern, add conversion function, then wire everything up at startup.

---

## Phase 1: Add Posh Adapter and Registration

### Overview
Add `search_events_adapter()` and `register_posh_source()` functions to firecrawl.py, following the patterns in eventbrite.py and exa_client.py.

### Changes Required:

#### 1.1 Add Posh Adapter Function

**File**: `api/services/firecrawl.py`
**Location**: After `get_posh_extractor()` (after line 367)

```python
async def search_events_adapter(profile: Any) -> list[ScrapedEvent]:
    """
    Adapter for registry pattern - searches Posh using a SearchProfile.

    Args:
        profile: SearchProfile with search criteria

    Returns:
        List of ScrapedEvent objects matching the profile
    """
    extractor = get_posh_extractor()

    # Hardcoded location for now - future refactor will add location to SearchProfile
    city = "columbus"

    # Fetch all events for the city
    events = await extractor.discover_events(city=city, limit=30)

    # Post-fetch filtering based on SearchProfile
    filtered_events = []
    for event in events:
        # Filter by time_window if specified
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    continue

        # Filter by free_only if specified
        if hasattr(profile, "free_only") and profile.free_only:
            if not event.is_free:
                continue

        filtered_events.append(event)

    return filtered_events
```

#### 1.2 Add Registration Function

**File**: `api/services/firecrawl.py`
**Location**: After the adapter function

```python
def register_posh_source() -> None:
    """Register Posh as an event source in the global registry."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="posh",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=25,  # Lower priority - scraping is slower than APIs
        description="Posh.vip nightlife and social events via Firecrawl scraping",
    )
    register_event_source(source)
```

#### 1.3 Add Missing Import

**File**: `api/services/firecrawl.py`
**Location**: Top of file, add to imports

```python
from typing import Any
```

Note: `os` is already imported at line 10.

### Success Criteria:

#### Automated Verification:
- [x] No import errors: `python -c "from api.services.firecrawl import search_events_adapter, register_posh_source"`
- [x] Type checking passes: `uv run mypy api/services/firecrawl.py --ignore-missing-imports`
- [x] Linting passes: `uv run ruff check api/services/firecrawl.py`

---

## Phase 2: Add ScrapedEvent Conversion in search.py

### Overview
Add a conversion function to transform `ScrapedEvent` to `EventResult`, and register "posh" in the conversion dispatcher.

### Changes Required:

#### 2.1 Add Import for ScrapedEvent

**File**: `api/agents/search.py`
**Location**: Line 22-26 imports section

Change:
```python
from api.services import (
    EventbriteEvent,
    ExaSearchResult,
    get_event_source_registry,
)
```

To:
```python
from api.services import (
    EventbriteEvent,
    ExaSearchResult,
    ScrapedEvent,
    get_event_source_registry,
)
```

#### 2.2 Add Conversion Function

**File**: `api/agents/search.py`
**Location**: After `_convert_exa_result()` (after line 123)

```python
def _convert_scraped_event(event: ScrapedEvent) -> EventResult:
    """Convert ScrapedEvent (Posh/Firecrawl) to EventResult format."""
    # Build location string
    location = event.venue_name or "TBD"
    if event.venue_address:
        location = f"{location}, {event.venue_address}"

    # Format date
    date_str = datetime.now().isoformat()
    if event.start_time:
        date_str = event.start_time.isoformat()

    return EventResult(
        id=f"posh-{event.event_id}",
        title=event.title,
        date=date_str,
        location=location,
        category=event.category,  # Usually "nightlife" for Posh
        description=event.description[:200] if event.description else "",
        is_free=event.is_free,
        price_amount=event.price_amount,
        distance_miles=5.0,  # Unknown from Posh
        url=event.url,
    )
```

#### 2.3 Update Conversion Dispatcher

**File**: `api/agents/search.py`
**Location**: In `_convert_source_results()` function (lines 173-191)

Change the conversion logic (around line 181-187):
```python
        try:
            if source_name == "eventbrite" and isinstance(result, EventbriteEvent):
                events.append(_convert_eventbrite_event(result))
            elif source_name == "exa" and isinstance(result, ExaSearchResult):
                events.append(_convert_exa_result(result))
            else:
                # Unknown source type - skip
                logger.debug("Skipping unknown result type from %s", source_name)
```

To:
```python
        try:
            if source_name == "eventbrite" and isinstance(result, EventbriteEvent):
                events.append(_convert_eventbrite_event(result))
            elif source_name == "exa" and isinstance(result, ExaSearchResult):
                events.append(_convert_exa_result(result))
            elif source_name == "posh" and isinstance(result, ScrapedEvent):
                events.append(_convert_scraped_event(result))
            else:
                # Unknown source type - skip
                logger.debug("Skipping unknown result type from %s", source_name)
```

### Success Criteria:

#### Automated Verification:
- [x] No import errors: `python -c "from api.agents.search import search_events"`
- [x] Type checking passes: `uv run mypy api/agents/search.py --ignore-missing-imports` (pre-existing errors on lines 312/315 unrelated to this change)
- [x] Linting passes: `uv run ruff check api/agents/search.py`

---

## Phase 3: Wire Up Registration at App Startup

### Overview
Call all registration functions when the FastAPI app starts, so event sources are available for searches.

### Changes Required:

#### 3.1 Add Registration Imports

**File**: `api/index.py`
**Location**: Line 21 imports section

Change:
```python
from api.agents.search import search_events
```

To:
```python
from api.agents.search import search_events
from api.services import (
    register_eventbrite_source,
    register_exa_source,
)
from api.services.firecrawl import register_posh_source
```

#### 3.2 Add Registration Calls

**File**: `api/index.py`
**Location**: After `configure_logging()` call (after line 35), before `app = FastAPI()`

```python
# Register event sources
register_eventbrite_source()
register_exa_source()
register_posh_source()
```

### Success Criteria:

#### Automated Verification:
- [x] No import errors: `python -c "from api.index import app"`
- [x] Server starts without errors: `timeout 5 uv run uvicorn api.index:app --host 127.0.0.1 --port 8765 || true`
- [x] Linting passes: `uv run ruff check api/index.py`

#### Manual Verification:
- [ ] Start server with `LOG_LEVEL=DEBUG uv run uvicorn api.index:app --reload`
- [ ] Verify startup logs show all three sources registered
- [ ] Perform a search and verify `🔍 [Search] Starting parallel fetch` shows sources

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the registration logs appear correctly before proceeding.

---

## Phase 4: Update Exports

### Overview
Export `register_posh_source` from the services package for consistency.

### Changes Required:

#### 4.1 Add Export to __init__.py

**File**: `api/services/__init__.py`
**Location**: Line 31-39, firecrawl imports section

Change:
```python
from .firecrawl import (
    FirecrawlClient,
    LumaEvent,
    LumaExtractor,
    PoshExtractor,
    ScrapedEvent,
    get_firecrawl_client,
    get_posh_extractor,
)
```

To:
```python
from .firecrawl import (
    FirecrawlClient,
    LumaEvent,
    LumaExtractor,
    PoshExtractor,
    ScrapedEvent,
    get_firecrawl_client,
    get_posh_extractor,
    register_posh_source,
)
```

#### 4.2 Add to __all__

**File**: `api/services/__init__.py`
**Location**: In `__all__` list (around line 84)

Add after `"get_posh_extractor"`:
```python
    "register_posh_source",
```

### Success Criteria:

#### Automated Verification:
- [x] Export works: `python -c "from api.services import register_posh_source"`
- [x] Linting passes: `uv run ruff check api/services/__init__.py`

---

## Testing Strategy

### Unit Tests:
- Verify `search_events_adapter` filters events correctly by time_window
- Verify `search_events_adapter` filters events correctly by free_only
- Verify `_convert_scraped_event` produces valid EventResult

### Integration Tests:
- Call `search_events()` with a SearchProfile and verify Posh events are included
- Verify deduplication works across all three sources

### Manual Testing Steps:
1. Start server with `LOG_LEVEL=DEBUG`
2. Verify all three sources are registered at startup
3. Send a chat message that triggers a search
4. Verify logs show all three sources being queried
5. If FIRECRAWL_API_KEY is not set, verify Posh is gracefully skipped

## Performance Considerations

- Posh discovery involves web scraping, which is slower than API calls
- `discover_events` fetches up to 30 events before filtering (may want to tune this)
- Post-fetch filtering discards events, so effective results may be fewer than other sources
- Priority 25 ensures Posh doesn't slow down the parallel fetch (all sources run concurrently anyway)

## Future Improvements

- **Location from SearchProfile**: Add location field to SearchProfile and use it instead of hardcoded "columbus"
- **Category mapping**: Map SearchProfile categories to Posh event types
- **Keyword search**: Filter by title/description matching keywords
- **Caching**: Cache Posh discovery results to reduce scraping frequency

## References

- Related research: `thoughts/shared/research/2026-01-11-event-source-registration-missing.md`
- Eventbrite adapter pattern: `api/services/eventbrite.py:428-486`
- Exa adapter pattern: `api/services/exa_client.py:353-421`
- Event source registry: `api/services/base.py:16-151`
