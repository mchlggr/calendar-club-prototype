---
date: 2026-01-12T07:53:19Z
researcher: Claude
git_commit: 9085e041a2e251fd3e175c5c09b35f922f7439e0
branch: main
repository: calendar-club-prototype
topic: "Search Agent Tool Architecture - Breaking Up search_events Into Multiple Specialized Tools"
tags: [research, codebase, search-agent, tools, exa, firecrawl, event-sources]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Search Agent Tool Architecture

**Date**: 2026-01-12T07:53:19Z
**Researcher**: Claude
**Git Commit**: 9085e041a2e251fd3e175c5c09b35f922f7439e0
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

How is the current search agent's `search_events` tool structured, and what would be needed to break it up into multiple specialized search tools (Exa Search, Meetup via Firecrawl, Eventbrite via Firecrawl, generic Firecrawl scraping, agentic Exa Research loop, etc.)?

## Summary

The current architecture has a **single `search_events` tool** that automatically queries ALL enabled event sources in parallel via a registry pattern. The tool is defined in `api/agents/orchestrator.py` and delegates to `api/agents/search.py` which uses the `EventSourceRegistry` to discover and query all enabled sources.

**Key finding**: The agent currently has NO control over which sources to query - the tool queries everything automatically. Breaking this into multiple tools would require:
1. Creating individual tool functions for each source/strategy
2. Updating the orchestrator agent's tool list
3. Modifying agent instructions to guide source selection
4. Potentially keeping a "search all" tool for broad queries

## Current Architecture

### Single Tool Design

The orchestrator agent has ONE search tool with THREE total tools:

```
api/agents/orchestrator.py:346-352
orchestrator_agent = Agent(
    tools=[search_events, refine_results, find_similar],
    ...
)
```

### Tool Definition

**Location**: `api/agents/orchestrator.py:99-124`

```python
@function_tool
async def search_events(profile: SearchProfile) -> SearchResult:
    """Search for events across ALL enabled sources.

    ALWAYS searches ALL sources in parallel (Eventbrite, Meetup, Exa, etc.)
    You do NOT select which sources to query.
    Results are automatically deduplicated.
    """
    return await _search_events(profile)
```

The tool accepts a `SearchProfile` with:
- `time_window: TimeWindow | None` - date range
- `categories: list[str]` - event types like "ai", "startup"
- `keywords: list[str]` - search terms
- `free_only: bool` - filter to free events
- `location` - defaults to Columbus, OH

### Parallel Source Execution

**Location**: `api/agents/search.py:437-480`

```python
registry = get_event_source_registry()
enabled_sources = registry.get_enabled()

tasks = []
for event_source in enabled_sources:
    tasks.append(event_source.search_fn(profile))

results = await asyncio.gather(*tasks, return_exceptions=True)
```

All enabled sources run in parallel via `asyncio.gather()`. Individual failures don't affect other sources.

## Event Source Registry

**Location**: `api/services/base.py:16-150`

### EventSource Dataclass

```python
@dataclass
class EventSource:
    name: str                                    # "exa", "meetup", etc.
    search_fn: Callable[..., Awaitable[list]]   # Async search function
    is_enabled_fn: Callable[[], bool] | None    # API key check
    priority: int = 100                          # Lower = queried first
    description: str = ""
```

### Current Source Priorities

| Priority | Source | Type | Status |
|----------|--------|------|--------|
| 10 | eventbrite | API | Disabled (deprecated) |
| 15 | meetup | GraphQL API | Commented out |
| 20 | exa | Neural search | **ENABLED** |
| 25 | posh | Firecrawl scrape | Commented out |
| 26 | luma | Firecrawl scrape | Commented out |
| 27 | partiful | Firecrawl scrape | Commented out |
| 28 | meetup_scraper | Firecrawl scrape | Commented out |
| 30 | exa-research | Agentic research | **ENABLED** |
| 30 | river | Firecrawl scrape | Commented out |

### Registration Pattern

**Location**: `api/index.py:49-59`

```python
# Currently enabled:
register_exa_source()           # Line 52
register_exa_research_source()  # Line 59

# Commented out:
# register_eventbrite_source()
# register_meetup_source()
# register_posh_source()
# etc.
```

## Exa Client Implementation

**Location**: `api/services/exa_client.py`

### ExaClient Class (lines 45-508)

Wraps the official `exa-py` SDK with async compatibility.

**Key Methods**:
- `search()` - Neural web search with optional LLM extraction
- `find_similar()` - Find pages similar to a reference URL
- `create_webset()` / `get_webset()` - Async deep discovery (raw HTTP)

### Search Flow

```python
async def search(
    query: str,
    num_results: int = 10,
    include_text: bool = True,
    extract_events: bool = False,  # Enables LLM extraction
    start_published_date: datetime | None = None,
    ...
) -> list[ExaSearchResult]
```

1. Wraps sync SDK in `run_in_threadpool()` for async
2. Calls `Exa.search_and_contents()` for neural search
3. Optionally enriches results with GPT-4o-mini extraction
4. Returns `list[ExaSearchResult]`

### Search Adapter (lines 542-599)

```python
async def search_events_adapter(profile: Any) -> list[ExaSearchResult]:
    # Builds natural language query from profile
    query_parts = ["events in Columbus, Ohio"]

    # Adds date range as natural language
    # "happening January 15-20, 2026"

    # Adds categories and keywords

    return await client.search(
        query,
        num_results=10,
        extract_events=True,  # LLM enrichment
    )
```

**Key Design Decision**: Date filtering is done via natural language in the query, NOT via Exa's date API params (which filter page publication date, not event date).

## Exa Research Client (Agentic Pattern)

**Location**: `api/services/exa_research.py`

### How It Differs from Regular Exa

| Aspect | ExaClient | ExaResearchClient |
|--------|-----------|-------------------|
| Execution | Immediate | Async with polling |
| API | `client.search()` | `client.research.create()` |
| Query type | Search query | Research instructions |
| Results | Raw search results | Structured extracted events |
| Extraction | Post-processing via OpenAI | During research via Exa LLM |
| Latency | Fast (~2 seconds) | Slow (up to 60 seconds) |
| Priority | 20 | 30 |

### Agentic Research Flow

```python
async def research_events_adapter(profile: Any) -> list[ExaSearchResult]:
    # 1. Build research instructions (not a search query)
    query_parts = [
        "Find upcoming events in Columbus, Ohio",
        "For each event, extract: title, date, time, venue, price, URL",
    ]

    # 2. Create research task WITH structured output schema
    task_id = await client.create_research_task(
        query,
        output_schema=ResearchEventsOutput,  # Pydantic model
    )

    # 3. Poll for results (max 60 seconds)
    for _ in range(12):
        await asyncio.sleep(5.0)
        status = await client.get_task_status(task_id)
        if status.status == "completed":
            return status.results

    return []  # Timeout
```

### Structured Output Schema (lines 31-66)

```python
class ResearchEventItem(BaseModel):
    title: str
    start_date: str  # "Month Day, Year" format
    start_time: str | None
    venue_name: str | None
    venue_address: str | None
    price: str = "Free"
    url: str
    description: str | None

class ResearchEventsOutput(BaseModel):
    events: list[ResearchEventItem]
```

The Pydantic model is passed to Exa's API, which constrains the LLM output.

## Firecrawl Extractors

**Location**: `api/services/firecrawl.py`

### Architecture

```
FirecrawlClient (lines 124-219)
    └── wraps AsyncFirecrawl SDK

BaseExtractor (lines 221-404)
    ├── PoshExtractor (posh.vip)
    ├── LumaExtractor (lu.ma)
    ├── PartifulExtractor (partiful.com)
    ├── MeetupExtractor (meetup.com)
    ├── FacebookExtractor (disabled)
    └── RiverExtractor (getriver.io)
```

### Base Extraction Schema (lines 43-121)

All extractors use a common JSON schema for LLM-guided extraction:

```python
BASE_EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "start_date": {"type": "string"},  # "Month Day, Year"
        "start_time": {"type": ["string", "null"]},
        "venue_name": {"type": ["string", "null"]},
        "venue_address": {"type": ["string", "null"]},
        "price": {"type": "string"},
        "image_url": {"type": ["string", "null"]},
    },
    "required": ["title", "start_date", "price"],
}
```

### Extractor Template Method Pattern

```python
class BaseExtractor:
    SOURCE_NAME = "unknown"
    BASE_URL = ""
    EVENT_SCHEMA = BASE_EVENT_SCHEMA

    # Abstract methods for subclasses:
    def _extract_event_id(self, url: str) -> str: ...
    def _parse_extracted_data(self, url: str, data: dict) -> ScrapedEvent | None: ...

    # Shared implementation:
    async def extract_event(self, url: str) -> ScrapedEvent | None:
        data = await self.client.scrape(url, extract_schema=self.EVENT_SCHEMA)
        return self._parse_extracted_data(url, data.get("extract", {}))

    async def _crawl_and_extract(self, discovery_url, limit, patterns):
        # Crawl discovery page, extract events from found URLs
```

### Platform-Specific Strategies

| Extractor | Discovery Method | URL Pattern |
|-----------|------------------|-------------|
| Posh | Crawl `/c/{city}` | `/e/*` |
| Luma | Scrape links, filter by path | Single-level paths |
| Partiful | Scrape `/discover/{city}` | `/e/*` |
| Meetup | Scrape `/find/?location=X` | `/*/events/*` |
| River | Scrape `/discovery/communities` | `/events/*` |

### Search Adapter Pattern

Each extractor has an adapter function:

```python
async def search_events_adapter(profile: Any) -> list[ScrapedEvent]:
    extractor = get_posh_extractor()

    # Discover events
    events = await extractor.discover_events(city="columbus", limit=30)

    # Post-filter by time window
    if profile.time_window:
        events = [e for e in events if in_time_range(e, profile.time_window)]

    # Post-filter by free_only
    if profile.free_only:
        events = [e for e in events if e.is_free]

    return events
```

## Result Conversion

**Location**: `api/agents/search.py:393-421`

All source-specific types are converted to unified `EventResult`:

```python
def _convert_source_results(source_name: str, results: list) -> list[EventResult]:
    for result in results:
        if source_name == "exa" and isinstance(result, ExaSearchResult):
            converted = _convert_exa_result(result)
        elif source_name == "posh" and isinstance(result, ScrapedEvent):
            converted = _convert_scraped_event(result)
        elif source_name == "meetup" and isinstance(result, MeetupEvent):
            converted = _convert_meetup_event(result)
        # etc.
```

## Potential Multi-Tool Architecture

To break `search_events` into multiple tools, you would create individual tools like:

### Option 1: Source-Specific Tools

```python
@function_tool
async def search_exa(profile: SearchProfile) -> SearchResult:
    """Search using Exa neural web search. Fast (~2s), broad coverage."""

@function_tool
async def search_exa_research(profile: SearchProfile) -> SearchResult:
    """Deep agentic research via Exa. Slow (~60s), comprehensive extraction."""

@function_tool
async def search_meetup(profile: SearchProfile) -> SearchResult:
    """Search Meetup.com for community events."""

@function_tool
async def scrape_eventbrite(profile: SearchProfile) -> SearchResult:
    """Scrape Eventbrite event pages via Firecrawl."""

@function_tool
async def scrape_website(url: str, profile: SearchProfile) -> SearchResult:
    """Scrape any website for events using Firecrawl extraction."""
```

### Option 2: Strategy-Based Tools

```python
@function_tool
async def search_neural(profile: SearchProfile) -> SearchResult:
    """Fast neural web search across the internet (Exa)."""

@function_tool
async def search_structured_apis(profile: SearchProfile) -> SearchResult:
    """Query structured event APIs (Meetup GraphQL, Eventbrite)."""

@function_tool
async def scrape_event_platforms(
    profile: SearchProfile,
    platforms: list[str] = ["posh", "luma", "partiful"]
) -> SearchResult:
    """Scrape specific event platforms via Firecrawl."""

@function_tool
async def research_events(profile: SearchProfile) -> SearchResult:
    """Deep agentic research with Exa Research API. Use for comprehensive discovery."""

@function_tool
async def search_all(profile: SearchProfile) -> SearchResult:
    """Query ALL enabled sources in parallel. Use for broad searches."""
```

### Option 3: Capability-Based Tools

```python
@function_tool
async def quick_search(profile: SearchProfile) -> SearchResult:
    """Fast search (~2s). Uses Exa neural search."""

@function_tool
async def deep_search(profile: SearchProfile) -> SearchResult:
    """Comprehensive search (~60s). Uses Exa Research + all scrapers."""

@function_tool
async def scrape_url(url: str) -> EventResult | None:
    """Extract event details from a specific URL."""

@function_tool
async def find_similar_events(event_url: str) -> SearchResult:
    """Find events similar to a reference event."""
```

## Code References

### Core Tool Definition
- `api/agents/orchestrator.py:99-124` - `search_events` tool
- `api/agents/orchestrator.py:346-352` - Agent tool list

### Search Implementation
- `api/agents/search.py:424-580` - Core `search_events()` function
- `api/agents/search.py:437-480` - Parallel source execution
- `api/agents/search.py:393-421` - Result type conversion

### Registry System
- `api/services/base.py:16-44` - `EventSource` dataclass
- `api/services/base.py:47-124` - `EventSourceRegistry` class
- `api/services/base.py:127-150` - Singleton pattern

### Exa Integration
- `api/services/exa_client.py:45-508` - `ExaClient` class
- `api/services/exa_client.py:542-599` - Search adapter
- `api/services/exa_client.py:602-615` - Source registration

### Exa Research
- `api/services/exa_research.py:69-180` - `ExaResearchClient` class
- `api/services/exa_research.py:195-257` - Research adapter with polling
- `api/services/exa_research.py:31-66` - Structured output models

### Firecrawl Extractors
- `api/services/firecrawl.py:124-219` - `FirecrawlClient` class
- `api/services/firecrawl.py:221-404` - `BaseExtractor` class
- `api/services/firecrawl.py:406-586` - `PoshExtractor`
- `api/services/firecrawl.py:589-800` - `LumaExtractor`
- `api/services/firecrawl.py:801-990` - `PartifulExtractor`
- `api/services/firecrawl.py:991-1159` - `MeetupExtractor`

### Application Startup
- `api/index.py:49-59` - Source registration calls

## Architecture Documentation

### Current Data Flow

```
User Query
    ↓
Orchestrator Agent
    ↓
search_events tool (single tool)
    ↓
_search_events() in search.py
    ↓
EventSourceRegistry.get_enabled()
    ↓
asyncio.gather(*[source.search_fn(profile) for source in enabled])
    ↓
[ExaAdapter, ExaResearchAdapter, ...]  (parallel)
    ↓
_convert_source_results() (type conversion)
    ↓
_deduplicate_events()
    ↓
_validate_events()
    ↓
SearchResult (unified response)
```

### Proposed Multi-Tool Flow

```
User Query
    ↓
Orchestrator Agent (decides which tools to use)
    ↓
┌─────────────────────────────────────────────────┐
│ Tool Selection (based on query characteristics) │
│                                                 │
│ "quick search" → search_exa                     │
│ "comprehensive" → search_exa_research           │
│ "meetup events" → search_meetup                 │
│ "specific URL" → scrape_url                     │
│ "broad search" → search_all                     │
└─────────────────────────────────────────────────┘
    ↓
Individual tool executes
    ↓
SearchResult
```

## Open Questions

1. **Tool Granularity**: How granular should tools be? Per-source, per-strategy, or per-capability?

2. **Agent Instructions**: How should the agent decide which tool(s) to use? Could use query analysis or let user specify.

3. **Parallel Execution**: Should the agent be able to call multiple search tools in parallel, or should there be a composite "search_all" tool?

4. **Tool Parameters**: Should tools accept source-specific parameters (e.g., city slugs for Luma) or keep the generic `SearchProfile`?

5. **Backwards Compatibility**: Should the current `search_events` tool be kept as an alias for "search all sources"?

6. **Firecrawl Generic Tool**: Should there be a tool that can scrape ANY URL, or only predefined platforms?
