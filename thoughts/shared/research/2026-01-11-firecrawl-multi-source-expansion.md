---
date: 2026-01-11T18:48:39-05:00
researcher: Claude
git_commit: 936886e69700bb81dc760f3eaa0efc28c5ab6416
branch: main
repository: mchlggr/calendar-club-prototype
topic: "Firecrawl Multi-Source Expansion for Posh, Luma, and Parallel Processing"
tags: [research, codebase, firecrawl, posh, luma, meetup, parallel, event-sources]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude
---

# Research: Firecrawl Multi-Source Expansion

**Date**: 2026-01-11T18:48:39-05:00
**Researcher**: Claude
**Git Commit**: 936886e69700bb81dc760f3eaa0efc28c5ab6416
**Branch**: main
**Repository**: mchlggr/calendar-club-prototype

## Research Question

How can we add additional Firecrawl sources (Posh, Luma) and debug issues with Firecrawl? How can we elegantly expand different sources and run Firecrawl requests in parallel to pull in event data? How do we get structured output similar to Exa?

## Summary

The codebase has a **well-architected event source registry pattern** that enables parallel querying of multiple sources. Firecrawl is currently implemented for Posh with a working `PoshExtractor`, but the event extraction within `discover_events()` is **sequential** (not parallel). Luma exists only as **type aliases** pointing to Posh classes. Meetup has a complete GraphQL client but is **not yet registered** as an event source. The system can be expanded by:

1. Creating source-specific extractors for Luma following the Posh pattern
2. Parallelizing the extraction loop within `discover_events()`
3. Registering Meetup in the event source registry
4. Adding a Firecrawl `/search` endpoint integration for Exa-like structured results

## Detailed Findings

### 1. Current Event Source Architecture

#### Registry Pattern (`api/services/base.py:16-151`)

The system uses a clean registry pattern where event sources are pluggable:

```python
@dataclass
class EventSource:
    name: str                                    # e.g., "posh", "eventbrite"
    search_fn: Callable[..., Awaitable[list[Any]]]  # Async search function
    is_enabled_fn: Callable[[], bool] | None     # Check if API key configured
    priority: int = 100                          # Lower = queried first
    description: str = ""
```

Sources are queried **in parallel** via `asyncio.gather()` at `api/agents/search.py:273`:

```python
results = await asyncio.gather(*tasks, return_exceptions=True)
```

#### Currently Registered Sources (`api/index.py:43-46`)

| Source | Priority | Status | File |
|--------|----------|--------|------|
| Eventbrite | 10 | Registered | `api/services/eventbrite.py` |
| Exa | 20 | Registered | `api/services/exa_client.py` |
| Posh | 25 | Registered | `api/services/firecrawl.py` |
| Meetup | - | **NOT registered** | `api/services/meetup.py` |
| Luma | - | **Aliases only** | `api/services/firecrawl.py:427-428` |

### 2. Firecrawl Implementation Analysis

#### FirecrawlClient (`api/services/firecrawl.py:43-150`)

**Core Methods:**
- `scrape(url, formats, extract_schema)` - Single page extraction (line 75-107)
- `crawl(url, max_depth, limit, include_patterns)` - Multi-page crawling (line 109-149)

**Configuration:**
- Base URL: `https://api.firecrawl.dev/v1` (hardcoded, line 21)
- Timeout: 60 seconds (hardcoded, line 65)
- Auth: Bearer token via `FIRECRAWL_API_KEY` environment variable

**Error Handling Gaps:**
- No retry logic for transient failures
- No rate limiting handling (429 status)
- HTTP errors bubble up via `raise_for_status()` (lines 101, 143)

#### PoshExtractor (`api/services/firecrawl.py:152-347`)

**Event Schema (lines 164-178):**
```python
EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},      # Required
        "description": {"type": "string"},
        "date": {"type": "string"},
        "time": {"type": "string"},
        "venue_name": {"type": "string"},
        "venue_address": {"type": "string"},
        "price": {"type": "string"},
        "image_url": {"type": "string"},
        "organizer": {"type": "string"},
    },
    "required": ["title"],
}
```

**discover_events() Flow (lines 303-346):**
1. Constructs city URL: `https://posh.vip/c/{city}`
2. Calls `crawl()` with `max_depth=1`, `include_patterns=["/e/*"]`
3. **Sequential loop** processes each URL one-by-one (lines 330-339)
4. Calls `extract_event()` for each URL **awaiting each before next**
5. Stops when limit reached

**Critical Finding - Sequential Processing:**
```python
# Lines 330-339 - This is SEQUENTIAL, not parallel
for page in pages:
    url = page.get("url", "")
    if "/e/" not in url:
        continue
    event = await self.extract_event(url)  # Awaits each one!
    if event:
        events.append(event)
        if len(events) >= limit:
            break
```

This means if crawl returns 25 event URLs and we want 20 events, we make up to 25 **sequential** API calls to extract each event. With 60s timeouts, this could take 25 minutes worst case.

#### Hardcoded Limitations

| Value | Location | Impact |
|-------|----------|--------|
| City: "columbus" | `firecrawl.py:383` | All searches return Columbus events only |
| Limit: 30 events | `firecrawl.py:386` | Max 30 events per search |
| Distance: 5.0 miles | `search.py:148` | Fake distance for all Posh events |
| Category: "nightlife" | `firecrawl.py:291` | All Posh events categorized as nightlife |

### 3. Luma Integration Status

**Current State: Aliases Only**

At `api/services/firecrawl.py:427-428`:
```python
LumaEvent = ScrapedEvent
LumaExtractor = PoshExtractor
```

**What Exists:**
- Type aliases for backward compatibility
- Exports in `api/services/__init__.py` (lines 33-34)
- Test coverage uses mocked Luma events in cache
- No dedicated Luma extractor class

**What's Missing:**
- No `LumaExtractor` with Lu.ma-specific logic
- No Lu.ma URL patterns (e.g., `lu.ma/*`)
- No registration as event source
- No Luma API key configuration

### 4. Meetup Integration Status

**Current State: Complete Client, Not Registered**

#### MeetupClient (`api/services/meetup.py:101-293`)

- Uses GraphQL API at `https://api.meetup.com/gql`
- Requires `MEETUP_ACCESS_TOKEN` via OAuth
- Complete `MeetupEvent` model with full field coverage
- Working `search_events()` method with geo-location support
- Comprehensive unit tests at `api/services/tests/test_meetup.py`

**What's Missing:**
- Not exported from `api/services/__init__.py`
- No `register_meetup_source()` function
- No `search_events_adapter()` for registry pattern
- Not called at app startup

### 5. Exa-Like Structured Output via Firecrawl `/search`

**Exa Pattern (`api/services/exa_client.py`):**

Exa provides structured search results with:
- Title, URL, score, published_date
- Full text content and highlights
- Domain filtering

**Firecrawl `/search` Endpoint:**

Firecrawl has a `/search` endpoint (not currently used) that provides web search + scrape:
- Credit cost: 2 per 10 results
- Returns structured results similar to Exa
- Could provide discovery without explicit URL crawling

**Current Usage:**
The codebase only uses `/scrape` and `/crawl` endpoints. The `/search` endpoint would enable:
- Keyword-based event discovery without knowing URLs
- Structured results similar to Exa
- Lower credit cost than crawl + extract per page

### 6. Parallel Processing Pattern

#### Current Search Parallelization (`api/agents/search.py:250-279`)

Sources are queried in parallel at the registry level:
```python
for source in enabled_sources:
    tasks.append(source.search_fn(profile))

results = await asyncio.gather(*tasks, return_exceptions=True)
```

#### Missing Internal Parallelization

Within `PoshExtractor.discover_events()`, extraction is sequential. For parallel:

```python
# Pattern for parallel extraction
async def discover_events_parallel(self, city: str, limit: int) -> list[ScrapedEvent]:
    pages = await self.client.crawl(url=city_url, ...)

    # Create extraction tasks
    tasks = [
        self.extract_event(page["url"])
        for page in pages
        if "/e/" in page.get("url", "")
    ]

    # Execute in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter successful results
    events = [r for r in results if isinstance(r, ScrapedEvent)]
    return events[:limit]
```

### 7. Adding New Source Pattern

To add a new Firecrawl-based source (e.g., Luma):

#### Step 1: Create Extractor Class

```python
class LumaExtractor:
    SOURCE_NAME = "luma"
    BASE_URL = "https://lu.ma"

    LUMA_EVENT_SCHEMA = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "start_date": {"type": "string"},
            "start_time": {"type": "string"},
            "location": {"type": "string"},
            "hosts": {"type": "array", "items": {"type": "string"}},
            "ticket_price": {"type": "string"},
            "cover_image": {"type": "string"},
        },
        "required": ["title"],
    }

    async def discover_events(self, search_term: str, limit: int = 20) -> list[ScrapedEvent]:
        # Lu.ma uses /discover or specific event URLs
        # Pattern: https://lu.ma/event-slug
        pass
```

#### Step 2: Create Adapter Function

```python
async def search_luma_adapter(profile: Any) -> list[ScrapedEvent]:
    extractor = get_luma_extractor()

    # Build search from profile
    search_term = " ".join(profile.keywords or ["tech"])

    events = await extractor.discover_events(search_term=search_term, limit=30)

    # Post-filter by time_window, free_only, etc.
    return filter_events(events, profile)
```

#### Step 3: Register Source

```python
def register_luma_source() -> None:
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="luma",
        search_fn=search_luma_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=26,  # After Posh
        description="Lu.ma events via Firecrawl scraping",
    )
    register_event_source(source)
```

#### Step 4: Add to Startup

```python
# api/index.py
from api.services.firecrawl import register_posh_source, register_luma_source

register_posh_source()
register_luma_source()
```

### 8. Conversion Functions

Each source type needs a conversion function in `api/agents/search.py`:

| Source | Model | Conversion Function |
|--------|-------|---------------------|
| Eventbrite | `EventbriteEvent` | `_convert_eventbrite_event()` (line 76) |
| Exa | `ExaSearchResult` | `_convert_exa_result()` (line 96) |
| Posh | `ScrapedEvent` | `_convert_scraped_event()` (line 127) |
| Meetup | `MeetupEvent` | **Not implemented** |
| Luma | `ScrapedEvent` | Uses Posh converter (same model) |

For Meetup, add:
```python
def _convert_meetup_event(event: MeetupEvent) -> EventResult:
    location = event.venue_name or "Online"
    if event.venue_address:
        location = f"{location}, {event.venue_address}"

    return EventResult(
        id=f"meetup-{event.id}",
        title=event.title,
        date=event.start_time.isoformat(),
        location=location,
        category=event.category,
        description=event.description[:200] if event.description else "",
        is_free=event.is_free,
        price_amount=event.price_amount,
        distance_miles=5.0,
        url=event.url,
    )
```

## Code References

### Core Files

- `api/services/firecrawl.py` - Firecrawl client and Posh extractor
- `api/services/base.py:16-151` - Event source registry pattern
- `api/agents/search.py:223-344` - Search orchestration with parallel sources
- `api/services/meetup.py` - Meetup GraphQL client (not registered)
- `api/services/exa_client.py` - Exa client (example of structured search)
- `api/index.py:43-46` - Source registration at startup

### Key Locations

| Component | File:Line |
|-----------|-----------|
| EventSource dataclass | `base.py:17-44` |
| Registry singleton | `base.py:126-140` |
| Parallel gather | `search.py:273` |
| Source conversion | `search.py:200-220` |
| PoshExtractor | `firecrawl.py:152-347` |
| Sequential loop | `firecrawl.py:330-339` |
| Hardcoded city | `firecrawl.py:383` |
| Luma aliases | `firecrawl.py:427-428` |
| MeetupClient | `meetup.py:101-210` |

## Architecture Documentation

### Current Data Flow

```
User Query → Chat Endpoint → Search Agent
                                    │
                         ┌──────────┼───────────┐
                         ▼          ▼           ▼
                    Eventbrite    Exa        Posh
                     (API)      (API)     (Firecrawl)
                         │          │           │
                         │          │     ┌─────┴─────┐
                         │          │     │ crawl()   │
                         │          │     ▼           │
                         │          │  URL list       │
                         │          │     │           │
                         │          │     ▼           │
                         │          │  [sequential]   │
                         │          │  extract_event  │
                         │          │  extract_event  │
                         │          │  extract_event  │
                         │          │     │           │
                         └──────────┼─────┴───────────┘
                                    ▼
                              asyncio.gather() ← Sources parallel
                                    │            Extraction sequential
                                    ▼
                           EventResult[] (deduped)
```

### Target Data Flow (with Luma + Parallel)

```
User Query → Chat Endpoint → Search Agent
                                    │
              ┌─────────┬───────────┼───────────┬─────────┐
              ▼         ▼           ▼           ▼         ▼
         Eventbrite   Exa        Posh        Luma     Meetup
           (API)    (API)    (Firecrawl) (Firecrawl) (GraphQL)
              │         │           │           │         │
              │         │     ┌─────┴───┐ ┌─────┴───┐     │
              │         │     │crawl()  │ │crawl()  │     │
              │         │     ▼         │ ▼         │     │
              │         │  URL list     │ URL list  │     │
              │         │     │         │     │     │     │
              │         │     ▼         │     ▼     │     │
              │         │  [PARALLEL]   │ [PARALLEL]│     │
              │         │  gather(      │ gather(   │     │
              │         │    extract,   │   extract,│     │
              │         │    extract,   │   extract,│     │
              │         │    ...)       │   ...)    │     │
              └─────────┴───────┴───────┴─────┴─────┴─────┘
                                    │
                              asyncio.gather()
                                    │
                           EventResult[] (deduped)
```

## Live Integration Tests

Testing infrastructure exists at `api/services/tests/test_live_sources.py`:

```bash
# Run all integration tests
pytest -m integration api/services/tests/test_live_sources.py -v

# Firecrawl only
pytest -m integration -k "Firecrawl or Posh" api/services/tests/test_live_sources.py -v
```

Test classes:
- `TestFirecrawlClientLive` - Tests scrape() and crawl() methods
- `TestPoshExtractorLive` - Tests discover_events() for Columbus and NYC

## Open Questions

1. **Lu.ma URL Discovery**: How to discover Lu.ma event URLs without crawling? Lu.ma doesn't have city listing pages like Posh.
2. **Firecrawl /search**: Should we use Firecrawl's search endpoint for discovery instead of crawling known sites?
3. **Rate Limiting**: Should we add exponential backoff for Firecrawl API errors?
4. **Parallel Limit**: How many concurrent extract_event() calls are safe without hitting rate limits?
5. **Meetup Auth**: OAuth flow for Meetup tokens needs to be implemented for end users.

## Related Research

- `thoughts/shared/research/2026-01-11-event-source-api-failures.md` - API failure analysis
- `throughts/research/2026-01-10-firecrawl-integration-research.md` - Original Firecrawl research
- `throughts/shared/plans/2026-01-11-event-source-registry-pattern.md` - Registry design
- `thoughts/shared/plans/2026-01-11-firecrawl-event-source-integration.md` - Posh integration plan
