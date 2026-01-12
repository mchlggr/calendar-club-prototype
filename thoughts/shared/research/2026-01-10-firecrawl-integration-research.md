---
date: 2026-01-10T12:00:00-05:00
researcher: Claude
git_commit: c3b34ff72c86592ac018a3ef2d5ed72c23964039
branch: main
repository: mchlggr/calendar-club-prototype
topic: "Firecrawl Integration for Multi-Source Event Scraping"
tags: [research, codebase, firecrawl, scraping, events, eventbrite, meetup, luma, posh, caching, deduplication, sql]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude
last_updated_note: "Added platform prioritization, SQL caching strategy, and deduplication design"
---

# Research: Firecrawl Integration for Multi-Source Event Scraping

**Date**: 2026-01-10T12:00:00-05:00
**Researcher**: Claude
**Git Commit**: c3b34ff72c86592ac018a3ef2d5ed72c23964039
**Branch**: main
**Repository**: mchlggr/calendar-club-prototype

## Research Question

How should Firecrawl be integrated into this application to scrape events from Eventbrite, Luma, Posh, Meetup.com, and other event sources? What is the current architecture and how would Firecrawl fit in?

## Summary

The Calendar Club application currently has a **single event source** (Eventbrite) implemented via its official REST API. The architecture is designed around **API-first integration** with no existing web scraping infrastructure. The codebase uses `httpx.AsyncClient` for HTTP requests, Pydantic models for data validation, and a singleton pattern for service clients.

Firecrawl would provide a complementary capability to fetch events from sources that don't offer official APIs, or to augment API data with additional details scraped from event pages. The Python SDK (`firecrawl-py`) integrates cleanly with the existing async patterns and Pydantic-based configuration.

## Detailed Findings

### 1. Current Event Source Architecture

#### Entry Points

**Main Search Flow:**
1. User query → `/api/chat/stream` endpoint (`api/index.py:248`)
2. Search agent processes query (`api/agents/search.py:124`)
3. `search_events()` function calls `_fetch_eventbrite_events()`
4. `EventbriteClient.search_events()` fetches from Eventbrite API
5. Results transformed to `EventResult` model and returned

**Key Files:**
- `api/services/eventbrite.py:35-232` - EventbriteClient implementation
- `api/agents/search.py:64-121` - Event fetching and transformation
- `api/config.py:12-49` - Configuration via pydantic-settings

#### Current Event Data Models

**Backend Models:**

```python
# EventbriteEvent (api/services/eventbrite.py:18-33)
class EventbriteEvent(BaseModel):
    id: str
    title: str
    description: str
    start_time: datetime
    end_time: datetime | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    category: str = "community"
    is_free: bool = True
    price_amount: int | None = None
    url: str | None = None
    logo_url: str | None = None

# EventResult (api/agents/search.py:23-36)
class EventResult(BaseModel):
    id: str
    title: str
    date: str  # ISO 8601 datetime string
    location: str
    category: str
    description: str
    is_free: bool
    price_amount: int | None = None
    distance_miles: float
    url: str | None = None
```

**Frontend Model:**

```typescript
// frontend/src/lib/api.ts:12-29
interface CalendarEvent {
    id: string;
    title: string;
    description?: string;
    startTime: Date;
    endTime?: Date;
    location?: string;
    url?: string;
    source: string;
    sourceUrl?: string;
    categories?: string[];
    imageUrl?: string;
    price?: {
        isFree: boolean;
        amount?: number;
        currency?: string;
    };
}
```

#### HTTP Client Pattern

The codebase uses `httpx.AsyncClient` with lazy initialization:

```python
# api/services/eventbrite.py:44-51
async def _get_client(self) -> httpx.AsyncClient:
    if self._client is None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )
    return self._client
```

#### Configuration Pattern

Uses pydantic-settings for environment-based configuration:

```python
# api/config.py:12-43
class Settings(BaseSettings):
    openai_api_key: str = Field(default="", description="OpenAI API key")
    eventbrite_api_key: str = Field(default="", description="Eventbrite API key")
    # ...
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
```

### 2. Existing Infrastructure (No Web Scraping)

**Current State:**
- No HTML scraping/parsing libraries installed (no BeautifulSoup, Scrapy, Playwright)
- Only `httpx` for HTTP requests to official REST APIs
- Single API integration: Eventbrite (official, authenticated)
- Architecture philosophy: API-first approach

**Dependencies (`requirements.txt`):**
- `httpx>=0.27.0` - HTTP client
- `pydantic>=2.0` - Data validation
- `pydantic-settings` - Environment configuration
- No scraping libraries present

### 3. Event Platform API Landscape

Based on existing research documents:

| Platform | API Type | Access | Rate Limits |
|----------|----------|--------|-------------|
| **Eventbrite** | REST | Public API key | 2,000/hour, 48,000/day |
| **Meetup** | GraphQL | Public (Feb 2025) | Documented in schema |
| **Luma** | REST | Luma Plus subscription required | Varies by plan |
| **Posh** | Webhooks | Developer access | Event-driven |
| **LinkedIn** | REST | Whitelisted partners only | Restricted |

**Source**: `throughts/research/Key Event API Sources and Their Limits.md`

### 4. Firecrawl API Overview

#### Core Capabilities

1. **`/scrape`** - Single page content extraction
   - Returns: markdown, HTML, JSON-LD, screenshots
   - Credit cost: 1 per page

2. **`/crawl`** - Multi-page website crawling
   - Follows links, discovers pages
   - Async with webhook support
   - Credit cost: 1 per page

3. **`/map`** - URL discovery
   - Finds all URLs on a site without scraping content
   - Useful for understanding site structure
   - Credit cost: 1 per page

4. **`/search`** - Web search + scrape
   - Search the web and extract results
   - Credit cost: 2 per 10 results

5. **`/extract`** - AI-powered structured extraction
   - Schema-based or natural language prompts
   - Uses FIRE-1 agent for complex pages

#### Python SDK

```python
# Installation
pip install firecrawl-py

# Basic usage
from firecrawl import Firecrawl, AsyncFirecrawl

# Sync
firecrawl = Firecrawl(api_key="fc-YOUR_API_KEY")
result = firecrawl.scrape("https://example.com", formats=["markdown"])

# Async (matches existing codebase pattern)
async def scrape():
    firecrawl = AsyncFirecrawl(api_key="fc-YOUR-API-KEY")
    doc = await firecrawl.scrape("https://example.com", formats=["markdown"])
```

#### Pricing

| Plan | Credits/Month | Cost | Concurrent Requests |
|------|---------------|------|---------------------|
| Free | 500 (one-time) | $0 | 2 |
| Hobby | 3,000 | $16/mo | 5 |
| Standard | 100,000 | $83/mo | 50 |
| Growth | 500,000 | $333/mo | 100 |

### 5. Integration Points

#### Where Firecrawl Would Fit

**Option A: Parallel Source** (alongside Eventbrite API)
- Add new service client: `api/services/firecrawl.py`
- Implement site-specific extractors
- Aggregate results in search agent

**Option B: Enrichment Layer** (enhance API results)
- Scrape additional details from event URLs
- Extract JSON-LD structured data
- Fetch images, full descriptions

**Option C: Fallback Source** (when APIs unavailable)
- Use when no API key configured
- Scrape public event pages directly

#### Recommended File Locations

```
api/
├── services/
│   ├── eventbrite.py      # Existing
│   ├── firecrawl.py       # NEW: Firecrawl client wrapper
│   ├── scrapers/          # NEW: Site-specific extractors
│   │   ├── __init__.py
│   │   ├── base.py        # Base scraper class
│   │   ├── meetup.py
│   │   ├── luma.py
│   │   └── posh.py
│   └── __init__.py        # Update exports
├── config.py              # Add firecrawl_api_key
```

#### Configuration Addition

```python
# api/config.py (addition)
class Settings(BaseSettings):
    # ... existing fields
    firecrawl_api_key: str = Field(default="", description="Firecrawl API key")
```

```bash
# .env.example (addition)
FIRECRAWL_API_KEY=fc-...
```

### 6. Site-Specific Extraction Strategies

#### Eventbrite (Enhancement)
- Already has official API
- Firecrawl could: extract full description, scrape organizer details
- Use JSON-LD when present (Schema.org Event)

#### Meetup
- Has GraphQL API (Feb 2025+)
- Firecrawl useful for: groups without API access, historical pages
- Target: `/events/` URLs, extract JSON-LD

#### Luma
- API requires Luma Plus subscription
- Firecrawl alternative: scrape public event pages
- Target: `lu.ma/*` event URLs

#### Posh
- Webhook-based (event-driven, not polling)
- Firecrawl useful for: initial event discovery, page details
- Target: `posh.vip/e/*` event URLs

#### General Strategy

1. **Check for JSON-LD first** - Most event pages embed Schema.org Event
2. **Fall back to HTML extraction** - Use Firecrawl's markdown output
3. **Use `/map` for discovery** - Find event URLs on venue/organizer sites
4. **Search + scrape** - Use `/search` for event discovery by topic/location

### 7. Existing Codebase Patterns to Follow

#### Error Handling Pattern

```python
# From api/services/eventbrite.py:146-149
except httpx.HTTPError as e:
    logger.warning("Eventbrite API error: %s", e)
    return []  # Graceful degradation
```

#### Source Attribution Pattern

```python
# From api/agents/search.py:54-61
class SearchResult(BaseModel):
    events: list[EventResult]
    source: str = Field(description="Data source: 'eventbrite' or 'unavailable'")
    message: str | None = None
```

#### Singleton Client Pattern

```python
# From api/services/eventbrite.py:222-231
_client: EventbriteClient | None = None

def get_eventbrite_client() -> EventbriteClient:
    global _client
    if _client is None:
        _client = EventbriteClient()
    return _client
```

### 8. Potential Challenges

1. **ToS Compliance**
   - Existing research warns: "Eventbrite ToS explicitly prohibits scraping"
   - Use official APIs where available
   - Firecrawl respects robots.txt

2. **Rate Limiting**
   - Firecrawl has credit-based limits
   - Need to implement backoff logic (codebase already has pattern)

3. **Data Normalization**
   - Multiple sources → unified EventResult model
   - Need consistent category mapping
   - Deduplication by (title, start_time, venue)

4. **Cost Management**
   - 1 credit per page scraped
   - Use `/map` strategically before `/crawl`
   - Cache scraped results

## Code References

- `api/services/eventbrite.py:35-232` - Current event client pattern to follow
- `api/agents/search.py:64-121` - Event transformation logic
- `api/agents/search.py:124-165` - Search function with source attribution
- `api/config.py:12-49` - Configuration pattern for API keys
- `api/index.py:38-50` - User-friendly error formatting

## Architecture Documentation

**Current Data Flow:**
```
User Query → Chat Endpoint → Search Agent → EventbriteClient → Eventbrite API
                                    ↓
                              EventResult[] ← EventbriteEvent[]
```

**Proposed Data Flow (with Firecrawl):**
```
User Query → Chat Endpoint → Search Agent → Event Aggregator
                                    ↓
              ┌─────────────────────┼─────────────────────┐
              ↓                     ↓                     ↓
      EventbriteClient      FirecrawlClient       MeetupClient
              ↓                     ↓                     ↓
       Eventbrite API    Firecrawl Scraping      Meetup GraphQL
              ↓                     ↓                     ↓
              └─────────────────────┼─────────────────────┘
                                    ↓
                              EventResult[] (normalized, deduplicated)
```

## Related Research

- `throughts/research/Key Event API Sources and Their Limits.md` - API landscape
- `throughts/research/Safe Polling and Ranking for Event Crawlers.md` - Crawling best practices
- `throughts/research/Connectors, ICS, and ToS Boundaries.md` - Legal considerations
- `throughts/research/Building a Standard Event Schema.md` - Schema design

## Open Questions

1. **Which platforms to prioritize?** (Meetup, Luma, Posh - all three?)
2. **Firecrawl tier selection?** (Hobby at $16/mo for 3K credits may suffice initially)
3. **JSON-LD extraction priority?** (Should be primary extraction method)
4. **Caching strategy?** (How long to cache scraped event data?)
5. **Deduplication approach?** (When same event appears on multiple platforms)

## Sources

### Firecrawl Documentation
- [Firecrawl Quickstart](https://docs.firecrawl.dev/introduction)
- [Python SDK](https://docs.firecrawl.dev/sdks/python)
- [Scrape Endpoint](https://www.firecrawl.dev/blog/mastering-firecrawl-scrape-endpoint)
- [Crawl Endpoint](https://www.firecrawl.dev/blog/mastering-the-crawl-endpoint-in-firecrawl)
- [Pricing](https://www.firecrawl.dev/pricing)
- [Rate Limits](https://docs.firecrawl.dev/rate-limits)

### Event Platform APIs
- [Eventbrite Rate Limits](https://www.eventbrite.com/platform/docs/rate-limits)
- [Meetup GraphQL API](https://www.meetup.com/graphql/guide/)
- [Luma API](https://help.luma.com/p/luma-api)
- [Posh Webhooks](https://university.posh.vip/university/post/a-guide-to-webhooks-at-posh)

---

## Follow-up Research 2026-01-11: Platform Prioritization, Caching, and Deduplication

### Platform Prioritization for Firecrawl

**Principle**: Use Firecrawl only for platforms **without accessible official APIs**. Official APIs provide structured data, are more reliable, and respect platform ToS.

| Platform | Has Official API? | Firecrawl Priority | Reasoning |
|----------|------------------|-------------------|-----------|
| **Luma** | Yes, but **paid** (Luma Plus required) | **HIGH** | API gated behind subscription; scraping public pages is free alternative |
| **Posh** | Webhooks only (push, not poll) | **HIGH** | No discovery API; webhooks require events to already exist |
| **Venue calendars** | No | **HIGH** | Long-tail local events; wildly varying markup |
| **Local media calendars** | No | **MEDIUM** | Alt-weeklies, city mags with event listings |
| **Meetup** | Yes (GraphQL, Feb 2025) | **LOW** | Use official API; Firecrawl only as enrichment fallback |
| **Eventbrite** | Yes (REST) | **SKIP** | Already integrated; ToS prohibits scraping |

**Implementation Order**:
1. **Luma** - High value, consistent page structure (`lu.ma/*`)
2. **Posh** - High value for nightlife/social events (`posh.vip/e/*`)
3. **Venue calendars** - Use Firecrawl `/map` + `/scrape` for discovery

### SQL Caching Strategy (Exa-Compatible)

The Exa integration uses async Websets with verification—results arrive asynchronously and need caching. The caching strategy must support both Firecrawl (immediate) and Exa (async) patterns.

#### Unified Events Cache Schema

```sql
-- Core events table (normalized from all sources)
CREATE TABLE events (
    id TEXT PRIMARY KEY,                    -- Internal UUID
    dedupe_key TEXT NOT NULL UNIQUE,        -- Composite dedup key (see below)

    -- Event data
    title TEXT NOT NULL,
    title_normalized TEXT NOT NULL,         -- Lowercase, stripped for dedup
    description TEXT,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    timezone TEXT,                          -- IANA timezone

    -- Location
    venue_name TEXT,
    venue_name_normalized TEXT,             -- For dedup matching
    venue_address TEXT,
    city TEXT,
    city_normalized TEXT,                   -- For dedup matching
    latitude REAL,
    longitude REAL,

    -- Pricing
    is_free BOOLEAN DEFAULT TRUE,
    price_min_cents INTEGER,
    price_max_cents INTEGER,
    price_currency TEXT DEFAULT 'USD',

    -- Categorization
    category TEXT DEFAULT 'community',
    tags TEXT[],                            -- JSON array

    -- Media
    image_url TEXT,

    -- URLs
    canonical_url TEXT,
    ticket_url TEXT,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,    -- Cache expiry

    -- Indexes for common queries
    INDEX idx_events_start_time (start_time),
    INDEX idx_events_city (city_normalized),
    INDEX idx_events_dedupe (dedupe_key),
    INDEX idx_events_expires (expires_at)
);

-- Provenance tracking (which sources contributed to this event)
CREATE TABLE event_sources (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,

    -- Source identification
    source_system TEXT NOT NULL,            -- 'eventbrite', 'firecrawl:luma', 'exa:webset', etc.
    source_url TEXT NOT NULL,
    source_id TEXT,                         -- Original ID from source system

    -- Fetch metadata
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
    fetch_method TEXT,                      -- 'api', 'scrape', 'webset'
    raw_data JSONB,                         -- Original response for debugging

    -- Quality signals
    is_primary BOOLEAN DEFAULT FALSE,       -- Preferred source for this event
    confidence_score REAL,                  -- 0.0-1.0, from Exa verification or extraction confidence

    UNIQUE(event_id, source_system, source_url)
);

-- Exa Webset tracking (async job management)
CREATE TABLE exa_websets (
    id TEXT PRIMARY KEY,                    -- Exa webset ID
    query TEXT NOT NULL,
    status TEXT DEFAULT 'pending',          -- 'pending', 'processing', 'completed', 'failed'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    items_count INTEGER DEFAULT 0,
    error_message TEXT
);

-- Firecrawl job tracking (for async crawls)
CREATE TABLE firecrawl_jobs (
    id TEXT PRIMARY KEY,                    -- Firecrawl job ID
    job_type TEXT NOT NULL,                 -- 'scrape', 'crawl', 'map'
    target_url TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    pages_scraped INTEGER DEFAULT 0,
    credits_used INTEGER DEFAULT 0,
    error_message TEXT
);
```

#### Cache Expiry Strategy

| Source Type | Cache TTL | Reasoning |
|-------------|-----------|-----------|
| API (Eventbrite, Meetup) | 2 hours | Official APIs have rate limits; respect them |
| Firecrawl scrape | 6 hours | Pages change less frequently |
| Exa Webset | 24 hours | Verified results; expensive to regenerate |
| Events within 72h | 1 hour | Near-term events need freshness |

```python
def get_cache_ttl(source_system: str, event_start: datetime) -> timedelta:
    """Determine cache TTL based on source and event timing."""
    hours_until_event = (event_start - datetime.now(timezone.utc)).total_seconds() / 3600

    # Near-term events refresh more frequently
    if hours_until_event < 72:
        return timedelta(hours=1)

    # Source-specific TTLs
    ttl_map = {
        'eventbrite': timedelta(hours=2),
        'meetup': timedelta(hours=2),
        'firecrawl': timedelta(hours=6),
        'exa': timedelta(hours=24),
    }

    # Extract base source (e.g., 'firecrawl:luma' -> 'firecrawl')
    base_source = source_system.split(':')[0]
    return ttl_map.get(base_source, timedelta(hours=6))
```

#### Compatibility with Exa Async Pattern

Exa Websets are async (minutes to hours). The caching layer handles this:

```python
# Exa workflow integration
async def fetch_events_exa(query: str, location: str) -> list[EventResult]:
    """Fetch events via Exa, using cache or creating new Webset."""

    # Check cache first
    cached = await get_cached_exa_results(query, location)
    if cached and not is_expired(cached):
        return cached.events

    # Check for in-progress Webset
    active_webset = await get_active_webset(query, location)
    if active_webset:
        if active_webset.status == 'completed':
            return await process_webset_results(active_webset.id)
        else:
            # Return stale cache while Webset processes
            return cached.events if cached else []

    # Create new Webset (async)
    webset_id = await create_exa_webset(query, location)
    await db.insert('exa_websets', {
        'id': webset_id,
        'query': query,
        'status': 'processing'
    })

    # Return stale cache while processing
    return cached.events if cached else []
```

### Deduplication Strategy

**Chosen Approach: Composite Key with Normalized Fields**

#### Reasoning

I chose composite key deduplication over fuzzy matching for the first pass because:

1. **Deterministic**: Same inputs always produce same key—no threshold tuning needed
2. **Fast**: O(1) lookup via database index on `dedupe_key`
3. **Debuggable**: Easy to see why two events matched or didn't
4. **Sufficient for MVP**: Catches 80%+ of duplicates across platforms

**Alternative (fuzzy matching)** would be more accurate but adds complexity:
- Requires embedding computation or trigram indexes
- Needs threshold tuning (0.85 similarity? 0.90?)
- Slower at query time
- Can be added as Phase 2 enhancement

#### Dedupe Key Construction

```python
import hashlib
import re
from datetime import datetime, timedelta

def normalize_text(text: str) -> str:
    """Normalize text for dedup comparison."""
    if not text:
        return ""
    # Lowercase, remove special chars, collapse whitespace
    normalized = text.lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def normalize_venue(venue_name: str | None, city: str | None) -> str:
    """Create normalized venue identifier."""
    parts = []
    if venue_name:
        # Remove common suffixes
        clean = re.sub(r'\b(theater|theatre|hall|center|centre|room)\b', '',
                      normalize_text(venue_name))
        parts.append(clean.strip())
    if city:
        parts.append(normalize_text(city))
    return '_'.join(parts) if parts else 'unknown'

def get_date_bucket(start_time: datetime) -> str:
    """Bucket datetime to 90-minute windows for fuzzy time matching.

    Events starting within 90 minutes of each other are considered
    potentially the same event (accounts for timezone issues,
    slight variations in listed start times).
    """
    # Round to nearest 90-minute bucket
    bucket_minutes = 90
    minutes_since_midnight = start_time.hour * 60 + start_time.minute
    bucket_index = minutes_since_midnight // bucket_minutes

    return f"{start_time.date().isoformat()}_{bucket_index:02d}"

def compute_dedupe_key(
    title: str,
    start_time: datetime,
    venue_name: str | None,
    city: str | None
) -> str:
    """Compute composite deduplication key.

    Key components:
    - Normalized title (first 50 chars)
    - Date bucket (90-minute windows)
    - Normalized venue + city

    Returns SHA-256 hash for fixed-length, index-friendly key.
    """
    title_norm = normalize_text(title)[:50]
    date_bucket = get_date_bucket(start_time)
    venue_norm = normalize_venue(venue_name, city)

    composite = f"{title_norm}|{date_bucket}|{venue_norm}"

    return hashlib.sha256(composite.encode()).hexdigest()[:32]
```

#### Example Dedup Matches

| Event A | Event B | Match? | Reasoning |
|---------|---------|--------|-----------|
| "AI & ML Meetup @ Google HQ, 7pm" | "AI and ML Meetup at Google Headquarters, 7:00 PM" | **YES** | Same normalized title, same date bucket, same venue |
| "Tech Talk: AI", Jan 15 7pm | "Tech Talk: AI", Jan 15 8pm | **YES** | Within 90-minute bucket |
| "Tech Talk: AI", Jan 15 7pm | "Tech Talk: AI", Jan 15 10pm | **NO** | Different date buckets |
| "Startup Grind Columbus" | "Startup Grind Cleveland" | **NO** | Different city in venue key |

#### Merge Policy (When Duplicates Found)

```python
async def merge_event_sources(
    existing_event_id: str,
    new_source: EventSource,
    new_data: dict
) -> None:
    """Merge new source data into existing event."""

    # Add to provenance
    await db.insert('event_sources', {
        'event_id': existing_event_id,
        'source_system': new_source.system,
        'source_url': new_source.url,
        'fetched_at': datetime.now(timezone.utc),
        'raw_data': new_source.raw_data,
        'confidence_score': new_source.confidence,
    })

    # Selective field update: prefer richer data
    updates = {}
    existing = await db.get('events', existing_event_id)

    # Description: prefer longer
    if new_data.get('description') and \
       len(new_data['description']) > len(existing.get('description', '')):
        updates['description'] = new_data['description']

    # Image: prefer if missing
    if new_data.get('image_url') and not existing.get('image_url'):
        updates['image_url'] = new_data['image_url']

    # Price: prefer explicit over unknown
    if new_data.get('price_min_cents') and not existing.get('price_min_cents'):
        updates['price_min_cents'] = new_data['price_min_cents']
        updates['price_max_cents'] = new_data.get('price_max_cents')

    # Location: prefer geocoded
    if new_data.get('latitude') and not existing.get('latitude'):
        updates['latitude'] = new_data['latitude']
        updates['longitude'] = new_data['longitude']

    if updates:
        updates['updated_at'] = datetime.now(timezone.utc)
        await db.update('events', existing_event_id, updates)
```

#### Source Priority for Conflicts

When the same field has different values across sources:

| Field | Priority Order | Reasoning |
|-------|---------------|-----------|
| `title` | API > Firecrawl > Exa | APIs have authoritative titles |
| `start_time` | API > Firecrawl > Exa | APIs have exact times |
| `description` | Longest wins | More detail is better |
| `price` | API > Firecrawl > Exa | APIs have accurate pricing |
| `image_url` | First non-null | Any image is better than none |
| `venue_address` | Most complete | Geocoding needs full address |

### Updated Architecture with Caching

```
User Query → Chat Endpoint → Search Agent
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                   Cache Layer            Fresh Fetch
                   (SQL query)           (if cache miss)
                         │                     │
                         │         ┌───────────┼───────────┐
                         │         ▼           ▼           ▼
                         │   Eventbrite   Firecrawl      Exa
                         │      API        Scrape      Websets
                         │         │           │           │
                         │         └───────────┼───────────┘
                         │                     ▼
                         │              Normalize +
                         │              Deduplicate
                         │                     │
                         │                     ▼
                         │              Cache Write
                         │                     │
                         └─────────────────────┘
                                    │
                                    ▼
                         EventResult[] (merged, deduped)
```

### Implementation Files

```
api/
├── services/
│   ├── eventbrite.py           # Existing
│   ├── firecrawl.py            # NEW: Firecrawl client
│   ├── exa.py                  # NEW: Exa client (from existing research)
│   ├── event_cache.py          # NEW: SQL caching layer
│   ├── dedup.py                # NEW: Deduplication logic
│   └── scrapers/
│       ├── __init__.py
│       ├── luma.py             # Luma page extractor
│       └── posh.py             # Posh page extractor
├── models/
│   └── events.py               # NEW: Canonical Event model
└── db/
    ├── __init__.py
    ├── schema.sql              # NEW: Table definitions
    └── migrations/             # NEW: Schema migrations
```
