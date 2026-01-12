---
date: 2026-01-11T23:58:25Z
researcher: michaelgeiger
git_commit: 936886e69700bb81dc760f3eaa0efc28c5ab6416
branch: main
repository: mchlggr/calendar-club-prototype
topic: "Exa and Firecrawl SDK Migration Research"
tags: [research, exa, firecrawl, sdk, migration, api]
status: complete
last_updated: 2026-01-11
last_updated_by: michaelgeiger
---

# Research: Exa and Firecrawl SDK Migration

**Date**: 2026-01-11T23:58:25Z
**Researcher**: michaelgeiger
**Git Commit**: 936886e69700bb81dc760f3eaa0efc28c5ab6416
**Branch**: main
**Repository**: mchlggr/calendar-club-prototype

## Research Question

The raw API implementations for Exa and Firecrawl are not working reliably. What are the official SDKs for these services, and how should we migrate from raw HTTP calls to using the official SDKs while preserving the existing registry-based event source architecture?

## Summary

Both Exa and Firecrawl offer official Python SDKs:

| Service | Package | Latest Version | Async Support |
|---------|---------|----------------|---------------|
| Exa | `exa-py` | 2.0.2 | **In development** (PR #59) - synchronous only in stable |
| Firecrawl | `firecrawl-py` | 4.12.0 | **Full support** via `AsyncFirecrawl` class |

**Key Finding**: The Firecrawl SDK is ready for migration with full async support. However, the Exa SDK currently lacks async support (only synchronous), which would require either running Exa calls in a thread pool or waiting for the async PR to merge.

## Current Implementation

### Exa Client (`api/services/exa_client.py`)

**Architecture**:
- Raw `httpx.AsyncClient` HTTP calls
- Base URL: `https://api.exa.ai`
- Authentication: `x-api-key` header
- Lazy initialization via `_get_client()` method

**Methods Implemented**:
| Method | Lines | Description |
|--------|-------|-------------|
| `search()` | 69-163 | Neural search with filters |
| `create_webset()` | 211-262 | Create async discovery job |
| `get_webset()` | 264-311 | Poll webset status |
| `_parse_search_result()` | 313-338 | Parse API response to model |

**Data Models**:
- `ExaSearchResult` (lines 20-31): id, title, url, score, published_date, author, text, highlights
- `ExaWebset` (lines 33-40): id, status, num_results, results

**Registry Integration**:
- Adapter: `search_events_adapter()` (lines 353-405)
- Registration: `register_exa_source()` (lines 408-422)
- Priority: 20

### Firecrawl Client (`api/services/firecrawl.py`)

**Architecture**:
- Raw `httpx.AsyncClient` HTTP calls
- Base URL: `https://api.firecrawl.dev/v1`
- Authentication: Bearer token
- 60-second timeout

**Methods Implemented**:
| Method | Lines | Description |
|--------|-------|-------------|
| `scrape()` | 75-107 | Single URL scrape with extraction |
| `crawl()` | 109-149 | Multi-page crawl |

**Posh Extractor** (`PoshExtractor` class, lines 152-347):
- LLM-based structured extraction
- Schema includes: title, description, date, time, venue_name, venue_address, price, image_url, organizer
- Date parsing via `dateparser` library
- Price parsing with free detection

**Registry Integration**:
- Adapter: `search_events_adapter()` (lines 370-407)
- Registration: `register_posh_source()` (lines 410-424)
- Priority: 25

## Official SDK Research

### Exa Python SDK (`exa-py`)

**Installation**: `pip install exa-py`

**Current Version**: 2.0.2 (Released December 19, 2025)

**Initialization**:
```python
from exa_py import Exa

exa = Exa(api_key="your-api-key")
# Or via environment variable
exa = Exa(os.getenv('EXA_API_KEY'))
```

**Available Methods**:
| Method | Description |
|--------|-------------|
| `search()` | Basic neural/keyword search |
| `search_and_contents()` | Search with content extraction |
| `find_similar()` | Find similar documents to URL |
| `find_similar_and_contents()` | Similar + content |
| `get_contents()` | Fetch content from URLs |
| `answer()` | Question answering |
| `stream_answer()` | Streaming Q&A |
| `research.create_task()` | Async research tasks |

**Search Parameters**:
- `query` (str): Search query
- `num_results` (int): Result count
- `type` (str): 'keyword' or 'neural'
- `include_domains` / `exclude_domains` (list)
- `start_published_date` / `end_published_date` (str, YYYY-MM-DD)
- `use_autoprompt` (bool)

**Async Support Status**:
- **NOT YET AVAILABLE** in stable release
- PR #59 "Add async python" opened January 29, 2025
- Partial async via `stream_answer()` and `research.create_task()`

**Sources**:
- PyPI: https://pypi.org/project/exa-py/
- GitHub: https://github.com/exa-labs/exa-py
- Docs: https://docs.exa.ai/sdks/python-sdk-specification

### Firecrawl Python SDK (`firecrawl-py`)

**Installation**: `pip install firecrawl-py`

**Current Version**: 4.12.0 (Released December 19, 2025)

**Initialization**:
```python
from firecrawl import Firecrawl, AsyncFirecrawl

# Sync client
firecrawl = Firecrawl(api_key="fc-YOUR_API_KEY")

# Async client
async_firecrawl = AsyncFirecrawl(api_key="fc-YOUR_API_KEY")
```

**Available Methods**:
| Method | Sync | Async | Description |
|--------|------|-------|-------------|
| `scrape()` | Yes | Yes | Single page scraping |
| `crawl()` | Yes | Yes | Full website crawl (blocking) |
| `start_crawl()` | Yes | Yes | Non-blocking crawl start |
| `get_crawl_status()` | Yes | Yes | Check crawl progress |
| `map()` | Yes | Yes | URL discovery |
| `extract()` | Yes | Yes | Structured extraction |
| `batch_scrape()` | Yes | Yes | Batch URL scraping |
| `watcher()` | N/A | Yes | Real-time crawl monitoring |

**Async Example**:
```python
import asyncio
from firecrawl import AsyncFirecrawl

async def main():
    firecrawl = AsyncFirecrawl(api_key="fc-YOUR-API-KEY")

    # Scrape with extraction
    result = await firecrawl.scrape(
        'https://posh.vip/e/event-slug',
        formats=[{
            "type": "json",
            "schema": EventSchema.model_json_schema()
        }]
    )

    # Crawl city page
    crawl = await firecrawl.crawl(
        'https://posh.vip/c/columbus',
        limit=30,
        scrape_options=ScrapeOptions(formats=['markdown'])
    )
```

**Structured Extraction with Pydantic**:
```python
from pydantic import BaseModel
from firecrawl import AsyncFirecrawl

class PoshEvent(BaseModel):
    title: str
    description: str | None
    date: str | None
    time: str | None
    venue_name: str | None
    venue_address: str | None
    price: str | None

result = await firecrawl.scrape(
    url,
    formats=[{
        "type": "json",
        "schema": PoshEvent.model_json_schema()
    }]
)
```

**Sources**:
- PyPI: https://pypi.org/project/firecrawl-py/
- GitHub: https://github.com/firecrawl/firecrawl
- Docs: https://docs.firecrawl.dev/sdks/python

## Migration Plan

### Phase 1: Firecrawl SDK Migration (Recommended First)

**Why First**: Full async support available, straightforward migration path.

**Changes Required**:

1. **Add dependency** to `requirements.txt`:
   ```
   firecrawl-py>=4.12.0
   ```

2. **Update `api/services/firecrawl.py`**:

   Replace `FirecrawlClient` class with SDK wrapper:
   ```python
   from firecrawl import AsyncFirecrawl
   from firecrawl.types import ScrapeOptions

   class FirecrawlClient:
       def __init__(self, api_key: str | None = None):
           self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
           self._client: AsyncFirecrawl | None = None

       def _get_client(self) -> AsyncFirecrawl:
           if self._client is None:
               self._client = AsyncFirecrawl(api_key=self.api_key)
           return self._client

       async def scrape(
           self,
           url: str,
           formats: list[str] | None = None,
           extract_schema: dict | None = None,
       ) -> dict:
           client = self._get_client()

           format_options = formats or ["markdown"]
           if extract_schema:
               format_options.append({
                   "type": "json",
                   "schema": extract_schema
               })

           result = await client.scrape(url, formats=format_options)
           return result

       async def crawl(
           self,
           url: str,
           max_depth: int = 2,
           limit: int = 10,
           include_patterns: list[str] | None = None,
           exclude_patterns: list[str] | None = None,
       ) -> list[dict]:
           client = self._get_client()

           result = await client.crawl(
               url,
               limit=limit,
               scrape_options=ScrapeOptions(formats=['markdown'])
           )
           return result.data if hasattr(result, 'data') else []
   ```

3. **Preserve existing interfaces**:
   - `PoshExtractor` class remains unchanged
   - `register_posh_source()` remains unchanged
   - `ScrapedEvent` model remains unchanged

**Files to Modify**:
- `requirements.txt`: Add `firecrawl-py>=4.12.0`
- `api/services/firecrawl.py`: Replace HTTP client with SDK

### Phase 2: Exa SDK Migration (Deferred - Async Pending)

**Challenge**: The official `exa-py` SDK is synchronous only. Options:

#### Option A: Thread Pool Wrapper (Immediate)

Wrap synchronous SDK calls in `asyncio.to_thread()`:

```python
from exa_py import Exa
import asyncio

class ExaClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        self._client: Exa | None = None

    def _get_client(self) -> Exa:
        if self._client is None:
            self._client = Exa(api_key=self.api_key)
        return self._client

    async def search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs
    ) -> list[ExaSearchResult]:
        client = self._get_client()

        # Run sync SDK in thread pool
        result = await asyncio.to_thread(
            client.search_and_contents,
            query,
            num_results=num_results,
            **kwargs
        )

        return [self._convert_result(r) for r in result.results]
```

**Pros**: Can migrate now
**Cons**: Thread pool overhead, not truly async

#### Option B: Wait for Async Support (Recommended)

Monitor PR #59 in `exa-labs/exa-py` for async support.

**Current Status** (as of 2026-01-11):
- PR #59 opened January 29, 2025
- Status: In development

**Recommendation**: Keep raw HTTP implementation for Exa until async SDK is released, then migrate.

### Phase 3: Websets API (Exa)

The Websets API used in `background_tasks.py` may not be fully supported by the SDK yet. Research needed on:
- `research.create_task()` as potential replacement
- Whether Websets endpoints are exposed in SDK

**Current Implementation** uses:
- `POST /websets/v0/websets` (create)
- `GET /websets/v0/websets/{id}` (poll)

If SDK doesn't support Websets, keep raw HTTP for that specific functionality.

## Files Affected by Migration

| File | Firecrawl Changes | Exa Changes |
|------|-------------------|-------------|
| `requirements.txt` | Add `firecrawl-py>=4.12.0` | Add `exa-py>=2.0.2` (when async ready) |
| `api/services/firecrawl.py` | Replace `FirecrawlClient` internals | N/A |
| `api/services/exa_client.py` | N/A | Replace `ExaClient` internals |
| `api/services/background_tasks.py` | N/A | May need raw HTTP for Websets |

## Recommendations

1. **Migrate Firecrawl first** - Full async SDK support makes this straightforward
2. **Keep Exa raw HTTP for now** - Async support pending in official SDK
3. **Preserve registry architecture** - Only change internal HTTP client, keep adapters and registration
4. **Monitor Exa PR #59** - Subscribe to updates for async support
5. **Test thoroughly** - Both services have integration tests in `test_live_sources.py`

## Code References

- `api/services/exa_client.py:42-339` - Current Exa HTTP client
- `api/services/firecrawl.py:43-150` - Current Firecrawl HTTP client
- `api/services/base.py:17-44` - EventSource registry pattern
- `api/services/tests/test_live_sources.py` - Integration tests

## Open Questions

1. Does the Exa SDK support the Websets API, or will we need to keep raw HTTP for that?
2. When will PR #59 (async support) be merged into `exa-py`?
3. Should we implement a hybrid approach where Firecrawl uses SDK but Exa stays raw until async is available?
