# Implementation Plan: Firecrawl Integration for Event Scraping

**Date**: 2026-01-11
**Status**: Ready for implementation

## Overview

Integrate Firecrawl to scrape events from platforms without accessible APIs, starting with Luma. Includes SQL caching compatible with Exa's async pattern and composite-key deduplication.

## Priority Order

1. **Luma** (HIGH) - API requires paid Luma Plus subscription
2. **Posh** (HIGH) - Webhooks only, no discovery API
3. **Venue calendars** (MEDIUM) - Future expansion

Skip: Eventbrite (already integrated), Meetup (has GraphQL API)

---

## Phase 1: Core Firecrawl Client + Luma Extractor

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `api/services/firecrawl.py` | CREATE | Firecrawl client + LumaExtractor |
| `api/config.py` | MODIFY | Add `firecrawl_api_key` field |
| `api/services/__init__.py` | MODIFY | Export new services |
| `pyproject.toml` | MODIFY | Add `firecrawl-py` dependency |

### Key Components

**ScrapedEvent Model** - Normalized event from any scraped source:
```python
class ScrapedEvent(BaseModel):
    id: str                          # e.g., "luma-evt-123"
    title: str
    description: str
    start_time: datetime
    end_time: datetime | None
    venue_name: str | None
    venue_address: str | None
    latitude: float | None
    longitude: float | None
    category: str = "community"
    is_free: bool = True
    price_amount: int | None
    url: str
    image_url: str | None
    source: str                      # "luma", "posh", etc.
```

**LumaExtractor** - Extracts events from `lu.ma/*` pages:
- Parses JSON embedded in Next.js `__NEXT_DATA__` script tag
- Handles `pageProps.initialData.events` structure
- Falls back to markdown parsing if JSON unavailable

**FirecrawlClient** - Async client following EventbriteClient pattern:
- Lazy `AsyncFirecrawl` initialization
- Singleton via `get_firecrawl_client()`
- Graceful degradation (returns `[]` on errors)

---

## Phase 2: SQL Caching Layer

### Files to Create

| File | Action | Purpose |
|------|--------|---------|
| `api/services/event_cache.py` | CREATE | SQLite caching + dedup |
| `api/services/tests/test_event_cache.py` | CREATE | Cache tests |

### Database Schema

```sql
-- Core events table
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,           -- "luma", "posh", "exa"
    title TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    venue_name TEXT,
    venue_address TEXT,
    latitude REAL,
    longitude REAL,
    category TEXT,
    is_free INTEGER,
    price_amount INTEGER,
    url TEXT,
    image_url TEXT,
    dedup_hash TEXT NOT NULL UNIQUE,
    scraped_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- Provenance tracking (Exa-compatible)
CREATE TABLE event_sources (
    event_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    scraped_at TEXT NOT NULL,
    PRIMARY KEY (event_id, source)
);

-- Job tracking for async operations
CREATE TABLE scrape_jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,           -- pending/running/completed/failed
    started_at TEXT,
    completed_at TEXT,
    event_count INTEGER DEFAULT 0
);
```

### Deduplication Strategy

**Composite key hash** (deterministic, fast, debuggable):
```python
def compute_dedup_hash(event: ScrapedEvent) -> str:
    key = f"{event.title.lower()}|{event.start_time.isoformat()}|{event.venue_address or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### Cache TTLs

| Source | TTL | Reasoning |
|--------|-----|-----------|
| Firecrawl | 6 hours | Pages change less frequently |
| Exa Webset | 24 hours | Verified, expensive to regenerate |
| Events < 72h | 1 hour | Near-term needs freshness |

---

## Phase 3: Search Agent Integration

### Files to Modify

| File | Action | Purpose |
|------|--------|---------|
| `api/agents/search.py` | MODIFY | Add `_fetch_firecrawl_events()`, merge sources |

### Integration Pattern

```python
async def search_events(profile: SearchProfile) -> SearchResult:
    all_events = []
    sources = []

    # Eventbrite (existing)
    if settings.eventbrite_api_key:
        eb_events = await _fetch_eventbrite_events(profile)
        all_events.extend(eb_events)
        if eb_events: sources.append("eventbrite")

    # Firecrawl cache (new)
    if settings.firecrawl_api_key:
        fc_events = await _fetch_firecrawl_events(profile)
        all_events.extend(fc_events)
        if fc_events: sources.append("luma")

    # Deduplicate and return
    unique = deduplicate_events(all_events)
    return SearchResult(events=unique[:10], source="+".join(sources))
```

---

## Phase 4: Posh Scraper + CLI

### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `api/services/firecrawl.py` | MODIFY | Add PoshExtractor class |
| `api/cli/scrape.py` | CREATE | CLI for manual/scheduled scraping |

### PoshExtractor

Target URLs: `posh.vip/e/*`

Structure TBD - will require investigation of Posh page markup.

### Scrape CLI

```bash
# Manual scraping for cache population
python -m api.cli.scrape sf --source luma
python -m api.cli.scrape nyc --source posh
```

---

## Verification Plan

### Unit Tests

1. **test_firecrawl.py**:
   - `LumaExtractor.can_handle()` URL matching
   - `LumaExtractor.extract_events()` JSON parsing
   - `FirecrawlClient` without API key returns `[]`

2. **test_event_cache.py**:
   - Dedup hash consistency
   - Store/retrieve roundtrip
   - Duplicate rejection on second store
   - Date range filtering

3. **test_search.py** (update existing):
   - Multi-source merging
   - Source attribution string

### Integration Test

```bash
# With FIRECRAWL_API_KEY set
pytest api/services/tests/test_firecrawl.py -v

# Full search flow
pytest api/agents/tests/test_search.py -v
```

### Manual Verification

```bash
# 1. Scrape Luma events
python -m api.cli.scrape sf --source luma

# 2. Check cache populated
sqlite3 api/event_cache.db "SELECT COUNT(*) FROM events"

# 3. Test search endpoint
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "events in San Francisco this weekend"}'

# 4. Verify source attribution includes "luma"
```

---

## Dependencies

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4
   │           │           │
   │           │           └── search.py integration
   │           └── event_cache.py (uses ScrapedEvent)
   └── firecrawl.py (foundation)
```

---

## Critical Files Reference

- `api/services/eventbrite.py` - Pattern for client structure
- `api/agents/search.py:64-165` - Integration point
- `api/config.py:12-43` - Config pattern
- `api/services/__init__.py` - Export pattern

---

## Related Research

- `throughts/research/2026-01-10-firecrawl-integration-research.md` - Full research with Exa caching strategy and dedup design
- `throughts/research/2026-01-10-exa-websets-event-search-research.md` - Exa integration research
- `throughts/research/Key Event API Sources and Their Limits.md` - Platform API landscape
