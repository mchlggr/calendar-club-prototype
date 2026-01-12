# Exa and Firecrawl SDK Migration Implementation Plan

## Overview

Migrate from raw HTTP API calls to official SDKs for both Exa and Firecrawl, improving reliability and maintainability. Additionally, add a new Exa Research source and refactor Firecrawl for extensibility to support multiple extractors.

## Current State Analysis

### Exa (`api/services/exa_client.py`)
- Raw `httpx.AsyncClient` HTTP calls
- Methods: `search()`, `find_similar()`, `create_webset()`, `get_webset()`
- Websets used in `background_tasks.py` for async deep discovery
- Registered as "exa" event source (priority 20)

### Firecrawl (`api/services/firecrawl.py`)
- Raw `httpx.AsyncClient` HTTP calls
- Methods: `scrape()`, `crawl()`
- Single extractor: `PoshExtractor` (hardcoded)
- Registered as "posh" event source (priority 25)

### Key Discoveries:
- Firecrawl SDK (`firecrawl-py` v4.12.0) has full async support via `AsyncFirecrawl`
- Exa SDK (`exa-py` v2.0.2) is synchronous only - requires `run_in_threadpool` wrapper
- Exa SDK has `research.create_task()` for async research (different from Websets)
- Websets API not exposed in Exa SDK - keep raw HTTP for that

## Desired End State

1. **Firecrawl**: Uses `AsyncFirecrawl` SDK with extensible extractor architecture
2. **Exa Search**: Uses `exa-py` SDK wrapped in `run_in_threadpool`
3. **Exa Websets**: Remains raw HTTP (SDK doesn't support)
4. **Exa Research**: New source using SDK's `research.create_task()`
5. All existing functionality preserved, tests passing

### Verification:
- `pytest api/services/tests/test_live_sources.py -m integration -v` passes
- All event sources register and return results
- No regressions in search flow

## What We're NOT Doing

- Migrating Exa Websets to SDK (not supported)
- Changing the registry pattern or event source architecture
- Adding new Firecrawl extractors (just preparing extensibility)
- Changing SSE or background task infrastructure

## Implementation Approach

Use a phased approach where each phase is independently testable. Firecrawl first (simpler, full async), then Exa Search (requires thread pool), then new Exa Research source.

---

## Phase 1: Firecrawl SDK Migration + Extensibility

### Overview
Replace raw HTTP with `AsyncFirecrawl` SDK and refactor for multiple extractors.

### Changes Required:

#### 1.1 Add Dependency

**File**: `requirements.txt`
**Changes**: Add firecrawl-py package

```
firecrawl-py>=4.12.0
```

#### 1.2 Refactor FirecrawlClient

**File**: `api/services/firecrawl.py`
**Changes**: Replace HTTP client with SDK wrapper, add base extractor class

```python
"""
Firecrawl-based web scraping for event discovery.

Provides extensible extractors for various event platforms using Firecrawl's
structured extraction capabilities via the official SDK.
"""

import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from firecrawl import AsyncFirecrawl
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ScrapedEvent(BaseModel):
    """Event data extracted from a web page."""

    source: str
    event_id: str
    title: str
    description: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    category: str = "community"
    is_free: bool = False
    price_amount: int | None = None
    url: str
    logo_url: str | None = None
    raw_data: dict[str, Any] | None = None


class FirecrawlClient:
    """
    Async client wrapper for Firecrawl SDK.

    Provides a thin wrapper around AsyncFirecrawl with lazy initialization
    and consistent error handling.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self._client: AsyncFirecrawl | None = None

    def _get_client(self) -> AsyncFirecrawl:
        """Get or create the SDK client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("FIRECRAWL_API_KEY not configured")
            self._client = AsyncFirecrawl(api_key=self.api_key)
        return self._client

    async def scrape(
        self,
        url: str,
        formats: list[str] | None = None,
        extract_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Scrape a single URL.

        Args:
            url: The URL to scrape
            formats: Output formats (e.g., ["markdown", "html"])
            extract_schema: JSON schema for structured extraction

        Returns:
            Scraped content with requested formats
        """
        client = self._get_client()

        format_list: list[Any] = list(formats) if formats else ["markdown"]

        # Add extraction format if schema provided
        if extract_schema:
            format_list.append({
                "type": "json",
                "schema": extract_schema
            })

        try:
            result = await client.scrape(url, formats=format_list)
            # SDK returns dict-like object, normalize to dict
            return dict(result) if result else {}
        except Exception as e:
            logger.error("Firecrawl scrape error for %s: %s", url, e)
            raise

    async def crawl(
        self,
        url: str,
        limit: int = 10,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Crawl a website starting from the given URL.

        Args:
            url: Starting URL
            limit: Maximum number of pages to crawl
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude

        Returns:
            List of scraped page data
        """
        client = self._get_client()

        try:
            result = await client.crawl(
                url,
                limit=limit,
                include_paths=include_patterns,
                exclude_paths=exclude_patterns,
            )
            # Extract data from crawl result
            if hasattr(result, 'data'):
                return list(result.data)
            return list(result) if result else []
        except Exception as e:
            logger.error("Firecrawl crawl error for %s: %s", url, e)
            raise


class BaseExtractor(ABC):
    """
    Base class for Firecrawl-based event extractors.

    Subclass this to create extractors for different event platforms.
    Each extractor defines its own extraction schema and parsing logic.
    """

    SOURCE_NAME: str = "unknown"
    BASE_URL: str = ""
    EVENT_SCHEMA: dict[str, Any] = {}
    DEFAULT_CATEGORY: str = "community"

    def __init__(self, client: FirecrawlClient | None = None):
        self.client = client or get_firecrawl_client()

    @abstractmethod
    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from URL. Must be implemented by subclass."""
        pass

    @abstractmethod
    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse extracted data into ScrapedEvent. Must be implemented by subclass."""
        pass

    async def extract_event(self, url: str) -> ScrapedEvent | None:
        """
        Extract event data from a single URL.

        Args:
            url: Event page URL

        Returns:
            ScrapedEvent if extraction successful, None otherwise
        """
        try:
            data = await self.client.scrape(
                url=url,
                formats=["extract"],
                extract_schema=self.EVENT_SCHEMA,
            )

            extracted = data.get("extract", {})
            if not extracted.get("title"):
                logger.warning("No title found in %s event: %s", self.SOURCE_NAME, url)
                return None

            return self._parse_extracted_data(url, extracted)

        except Exception as e:
            logger.error("Failed to extract %s event from %s: %s", self.SOURCE_NAME, url, e)
            return None

    async def discover_events(
        self,
        discovery_url: str,
        limit: int = 20,
        include_patterns: list[str] | None = None,
    ) -> list[ScrapedEvent]:
        """
        Discover events by crawling a listing page.

        Args:
            discovery_url: URL to crawl for event links
            limit: Maximum number of events to return
            include_patterns: URL patterns to include (e.g., ["/e/*"])

        Returns:
            List of discovered events
        """
        try:
            pages = await self.client.crawl(
                url=discovery_url,
                limit=limit + 5,  # Buffer for failures
                include_patterns=include_patterns,
            )

            events = []
            for page in pages:
                url = page.get("url", "") if isinstance(page, dict) else getattr(page, 'url', '')
                if not url:
                    continue

                event = await self.extract_event(url)
                if event:
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d %s events", len(events), self.SOURCE_NAME)
            return events

        except Exception as e:
            logger.error("Failed to discover %s events: %s", self.SOURCE_NAME, e)
            return []
```

#### 1.3 Refactor PoshExtractor to Use Base Class

**File**: `api/services/firecrawl.py` (continued)
**Changes**: PoshExtractor extends BaseExtractor

```python
class PoshExtractor(BaseExtractor):
    """
    Extractor for Posh (posh.vip) events.

    Posh is a social events platform popular for nightlife,
    parties, and social gatherings.
    """

    SOURCE_NAME = "posh"
    BASE_URL = "https://posh.vip"
    DEFAULT_CATEGORY = "nightlife"

    EVENT_SCHEMA = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Event title"},
            "description": {"type": "string", "description": "Event description"},
            "date": {"type": "string", "description": "Event date (e.g., 'Saturday, Jan 15')"},
            "time": {"type": "string", "description": "Event time (e.g., '10 PM - 2 AM')"},
            "venue_name": {"type": "string", "description": "Venue name"},
            "venue_address": {"type": "string", "description": "Venue address"},
            "price": {"type": "string", "description": "Ticket price (e.g., 'Free', '$20')"},
            "image_url": {"type": "string", "description": "Event image URL"},
            "organizer": {"type": "string", "description": "Event organizer name"},
        },
        "required": ["title"],
    }

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Posh URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path.startswith("e/"):
            return path[2:]
        return path or url

    def _parse_datetime(
        self, date_str: str | None, time_str: str | None
    ) -> tuple[datetime | None, datetime | None]:
        """Parse Posh date/time strings into datetime objects."""
        if not date_str:
            return None, None

        try:
            import dateparser

            combined = date_str
            if time_str:
                time_parts = re.split(r"\s*[-–to]\s*", time_str, maxsplit=1)
                start_time = time_parts[0].strip()
                combined = f"{date_str} {start_time}"

            start_dt = dateparser.parse(
                combined,
                settings={"PREFER_DATES_FROM": "future"},
            )

            end_dt = None
            if time_str and ("-" in time_str or "–" in time_str or " to " in time_str.lower()):
                time_parts = re.split(r"\s*[-–]\s*|\s+to\s+", time_str, flags=re.IGNORECASE)
                if len(time_parts) > 1:
                    end_time = time_parts[1].strip()
                    end_combined = f"{date_str} {end_time}"
                    end_dt = dateparser.parse(
                        end_combined,
                        settings={"PREFER_DATES_FROM": "future"},
                    )

            return start_dt, end_dt

        except Exception as e:
            logger.warning("Failed to parse datetime: %s %s - %s", date_str, time_str, e)
            return None, None

    def _parse_price(self, price_str: str | None) -> tuple[bool, int | None]:
        """Parse price string into is_free and price_amount."""
        if not price_str:
            return True, None

        price_lower = price_str.lower().strip()
        if price_lower in ("free", "no cover", "complimentary", ""):
            return True, None

        match = re.search(r"\$?(\d+(?:\.\d{2})?)", price_str)
        if match:
            price = float(match.group(1))
            return False, int(price * 100)

        return True, None

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Posh extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime(
            extracted.get("date"),
            extracted.get("time"),
        )
        is_free, price_amount = self._parse_price(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted["title"],
            description=extracted.get("description", ""),
            start_time=start_dt,
            end_time=end_dt,
            venue_name=extracted.get("venue_name"),
            venue_address=extracted.get("venue_address"),
            category=self.DEFAULT_CATEGORY,
            is_free=is_free,
            price_amount=price_amount,
            url=url,
            logo_url=extracted.get("image_url"),
            raw_data=extracted,
        )

    async def discover_events(
        self,
        city: str = "columbus",
        limit: int = 20,
    ) -> list[ScrapedEvent]:
        """
        Discover events from Posh for a given city.

        Args:
            city: City slug (e.g., "columbus", "new-york")
            limit: Maximum number of events to return

        Returns:
            List of discovered events
        """
        from urllib.parse import urljoin
        city_url = urljoin(self.BASE_URL, f"/c/{city}")

        return await super().discover_events(
            discovery_url=city_url,
            limit=limit,
            include_patterns=["/e/*"],
        )
```

#### 1.4 Update Singleton and Registration

**File**: `api/services/firecrawl.py` (continued)
**Changes**: Keep existing patterns, update to use new classes

```python
# Singleton instances
_firecrawl_client: FirecrawlClient | None = None
_posh_extractor: PoshExtractor | None = None


def get_firecrawl_client() -> FirecrawlClient:
    """Get the singleton Firecrawl client."""
    global _firecrawl_client
    if _firecrawl_client is None:
        _firecrawl_client = FirecrawlClient()
    return _firecrawl_client


def get_posh_extractor() -> PoshExtractor:
    """Get the singleton Posh extractor."""
    global _posh_extractor
    if _posh_extractor is None:
        _posh_extractor = PoshExtractor()
    return _posh_extractor


async def search_events_adapter(profile: Any) -> list[ScrapedEvent]:
    """
    Adapter for registry pattern - searches Posh using a SearchProfile.
    """
    extractor = get_posh_extractor()
    city = "columbus"  # TODO: Extract from profile.location

    events = await extractor.discover_events(city=city, limit=30)

    # Post-fetch filtering
    filtered_events = []
    for event in events:
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    continue

        if hasattr(profile, "free_only") and profile.free_only:
            if not event.is_free:
                continue

        filtered_events.append(event)

    return filtered_events


def register_posh_source() -> None:
    """Register Posh as an event source in the global registry."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="posh",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=25,
        description="Posh.vip nightlife and social events via Firecrawl scraping",
    )
    register_event_source(source)


# Backward compatibility aliases
LumaEvent = ScrapedEvent
LumaExtractor = PoshExtractor
```

### Success Criteria:

#### Automated Verification:
- [x] `pip install -r requirements.txt` succeeds with firecrawl-py
- [x] `pytest api/services/tests/test_live_sources.py -k "Firecrawl or Posh" -m integration -v` passes
- [x] Type checking passes (if configured)
- [x] Import check: `python -c "from api.services.firecrawl import get_posh_extractor; print('OK')"`

#### Manual Verification:
- [ ] Run search flow and verify Posh events appear in results
- [ ] Check logs for successful Firecrawl SDK calls (no raw HTTP errors)

**Implementation Note**: After completing this phase and automated verification passes, pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Exa SDK Migration (Search Only)

### Overview
Replace Exa Search HTTP calls with SDK, keeping Websets as raw HTTP.

### Changes Required:

#### 2.1 Add Dependency

**File**: `requirements.txt`
**Changes**: Add exa-py package

```
exa-py>=2.0.2
```

#### 2.2 Refactor ExaClient

**File**: `api/services/exa_client.py`
**Changes**: Use SDK for search methods, keep raw HTTP for Websets

```python
"""
Exa API client for event discovery.

Uses official exa-py SDK for Search API (wrapped in thread pool for async),
and raw HTTP for Websets API (not supported by SDK).
"""

import logging
import os
import time
from datetime import datetime
from typing import Any

import httpx
from exa_py import Exa
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


class ExaSearchResult(BaseModel):
    """Parsed search result from Exa API."""

    id: str
    title: str
    url: str
    score: float | None = None
    published_date: datetime | None = None
    author: str | None = None
    text: str | None = None
    highlights: list[str] | None = None


class ExaWebset(BaseModel):
    """Webset status from Exa API."""

    id: str
    status: str  # "running", "completed", "failed"
    num_results: int | None = None
    results: list[ExaSearchResult] | None = None


class ExaClient:
    """
    Async client for Exa API.

    Uses official SDK for Search API (sync SDK wrapped in thread pool).
    Uses raw HTTP for Websets API (not supported by SDK).
    """

    BASE_URL = "https://api.exa.ai"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        self._sdk_client: Exa | None = None
        self._http_client: httpx.AsyncClient | None = None

    def _get_sdk_client(self) -> Exa:
        """Get or create the SDK client (synchronous)."""
        if self._sdk_client is None:
            if not self.api_key:
                raise ValueError("EXA_API_KEY not configured")
            self._sdk_client = Exa(api_key=self.api_key)
        return self._sdk_client

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for Websets (async)."""
        if self._http_client is None:
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            self._http_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=headers,
                timeout=30.0,
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _convert_sdk_result(self, result: Any) -> ExaSearchResult:
        """Convert SDK result object to our model."""
        published_date = None
        if hasattr(result, 'published_date') and result.published_date:
            try:
                if isinstance(result.published_date, str):
                    published_date = datetime.fromisoformat(
                        result.published_date.replace("Z", "+00:00")
                    )
                else:
                    published_date = result.published_date
            except ValueError:
                pass

        return ExaSearchResult(
            id=getattr(result, 'id', '') or getattr(result, 'url', ''),
            title=getattr(result, 'title', 'Untitled'),
            url=result.url,
            score=getattr(result, 'score', None),
            published_date=published_date,
            author=getattr(result, 'author', None),
            text=getattr(result, 'text', None),
            highlights=getattr(result, 'highlights', None),
        )

    def _sync_search(
        self,
        query: str,
        num_results: int,
        include_text: bool,
        include_highlights: bool,
        start_published_date: str | None,
        end_published_date: str | None,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[Any]:
        """Synchronous search using SDK (called via run_in_threadpool)."""
        client = self._get_sdk_client()

        kwargs: dict[str, Any] = {
            "num_results": num_results,
        }

        if start_published_date:
            kwargs["start_published_date"] = start_published_date
        if end_published_date:
            kwargs["end_published_date"] = end_published_date
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains

        # Use search_and_contents if we need text/highlights
        if include_text or include_highlights:
            result = client.search_and_contents(query, **kwargs)
        else:
            result = client.search(query, **kwargs)

        return result.results if hasattr(result, 'results') else []

    async def search(
        self,
        query: str,
        num_results: int = 10,
        include_text: bool = True,
        include_highlights: bool = True,
        start_published_date: datetime | None = None,
        end_published_date: datetime | None = None,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[ExaSearchResult]:
        """
        Search the web using Exa's neural search.

        Uses SDK wrapped in thread pool for async compatibility.
        """
        if not self.api_key:
            logger.warning("EXA_API_KEY not set, returning empty results")
            return []

        try:
            logger.debug(
                "🌐 [Exa] Starting search | query=%s num_results=%d",
                query[:50],
                num_results,
            )
            start_time = time.perf_counter()

            # Format dates for SDK
            start_date_str = start_published_date.strftime("%Y-%m-%d") if start_published_date else None
            end_date_str = end_published_date.strftime("%Y-%m-%d") if end_published_date else None

            # Run sync SDK in thread pool
            raw_results = await run_in_threadpool(
                self._sync_search,
                query,
                num_results,
                include_text,
                include_highlights,
                start_date_str,
                end_date_str,
                include_domains,
                exclude_domains,
            )

            results = [self._convert_sdk_result(r) for r in raw_results]

            elapsed = time.perf_counter() - start_time
            if results:
                logger.debug(
                    "✅ [Exa] Complete | results=%d duration=%.2fs",
                    len(results),
                    elapsed,
                )
            else:
                logger.debug("📭 [Exa] No results | duration=%.2fs", elapsed)

            return results

        except Exception as e:
            logger.warning("Exa search error: %s", e)
            return []

    def _sync_find_similar(
        self,
        url: str,
        num_results: int,
        include_text: bool,
        exclude_source_domain: bool,
    ) -> list[Any]:
        """Synchronous find_similar using SDK."""
        client = self._get_sdk_client()

        kwargs: dict[str, Any] = {
            "num_results": num_results,
            "exclude_source_domain": exclude_source_domain,
        }

        if include_text:
            result = client.find_similar_and_contents(url, **kwargs)
        else:
            result = client.find_similar(url, **kwargs)

        return result.results if hasattr(result, 'results') else []

    async def find_similar(
        self,
        url: str,
        num_results: int = 10,
        include_text: bool = True,
        exclude_source_domain: bool = True,
    ) -> list[ExaSearchResult]:
        """Find pages similar to a given URL."""
        if not self.api_key:
            return []

        try:
            raw_results = await run_in_threadpool(
                self._sync_find_similar,
                url,
                num_results,
                include_text,
                exclude_source_domain,
            )

            return [self._convert_sdk_result(r) for r in raw_results]

        except Exception as e:
            logger.warning("Exa findSimilar error: %s", e)
            return []

    # ========================================
    # Websets API (raw HTTP - SDK doesn't support)
    # ========================================

    async def create_webset(
        self,
        query: str,
        count: int = 50,
        criteria: str | None = None,
    ) -> str | None:
        """
        Create a Webset for async deep discovery.

        NOTE: Uses raw HTTP because SDK doesn't expose Websets API.
        """
        if not self.api_key:
            return None

        client = await self._get_http_client()

        payload: dict[str, Any] = {
            "query": query,
            "count": count,
        }

        if criteria:
            payload["criteria"] = criteria

        try:
            logger.debug(
                "🚀 [Exa] Creating Webset | query=%s count=%d",
                query[:50],
                count,
            )
            response = await client.post("/websets", json=payload)
            response.raise_for_status()
            data = response.json()

            webset_id = data.get("id")
            if webset_id:
                logger.debug("✅ [Exa] Webset created | id=%s", webset_id)
            return webset_id

        except httpx.HTTPError as e:
            logger.debug("❌ [Exa] Webset creation failed | error=%s", str(e)[:100])
            logger.warning("Exa create webset error: %s", e)
            return None

    async def get_webset(self, webset_id: str) -> ExaWebset | None:
        """
        Get the status and results of a Webset.

        NOTE: Uses raw HTTP because SDK doesn't expose Websets API.
        """
        if not self.api_key:
            return None

        client = await self._get_http_client()

        try:
            logger.debug("⏳ [Exa] Polling Webset | id=%s", webset_id)
            response = await client.get(f"/websets/{webset_id}")
            response.raise_for_status()
            data = response.json()

            results = None
            if data.get("results"):
                results = [
                    result
                    for result_data in data["results"]
                    if (result := self._parse_webset_result(result_data))
                ]

            status = data.get("status", "unknown")
            logger.debug(
                "📊 [Exa] Webset status | id=%s status=%s results=%s",
                webset_id,
                status,
                len(results) if results else 0,
            )

            return ExaWebset(
                id=data["id"],
                status=status,
                num_results=data.get("numResults"),
                results=results,
            )

        except httpx.HTTPError as e:
            logger.debug("❌ [Exa] Webset poll failed | id=%s error=%s", webset_id, str(e)[:100])
            logger.warning("Exa get webset error: %s", e)
            return None

    def _parse_webset_result(self, data: dict[str, Any]) -> ExaSearchResult | None:
        """Parse raw Webset result into ExaSearchResult."""
        try:
            published_date = None
            if data.get("publishedDate"):
                try:
                    published_date = datetime.fromisoformat(
                        data["publishedDate"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            return ExaSearchResult(
                id=data.get("id", data.get("url", "")),
                title=data.get("title", "Untitled"),
                url=data["url"],
                score=data.get("score"),
                published_date=published_date,
                author=data.get("author"),
                text=data.get("text"),
                highlights=data.get("highlights"),
            )

        except (KeyError, ValueError) as e:
            logger.warning("Error parsing Exa webset result: %s", e)
            return None


# Rest of file (singleton, adapter, registration) remains unchanged
```

#### 2.3 Keep Existing Singleton and Registration

**File**: `api/services/exa_client.py` (continued)
**Changes**: No changes to singleton pattern or registration

```python
# Singleton instance
_client: ExaClient | None = None


def get_exa_client() -> ExaClient:
    """Get the singleton Exa client."""
    global _client
    if _client is None:
        _client = ExaClient()
    return _client


async def search_events_adapter(profile: Any) -> list[ExaSearchResult]:
    """Adapter for registry pattern - searches Exa using a SearchProfile."""
    # ... (unchanged from current implementation)


def register_exa_source() -> None:
    """Register Exa as an event source in the global registry."""
    # ... (unchanged from current implementation)
```

### Success Criteria:

#### Automated Verification:
- [x] `pip install -r requirements.txt` succeeds with exa-py
- [x] `pytest api/services/tests/test_live_sources.py -k "Exa" -m integration -v` passes
- [x] Import check: `python -c "from api.services.exa_client import get_exa_client; print('OK')"`

#### Manual Verification:
- [ ] Run search flow and verify Exa events appear in results
- [ ] Verify Websets still work (background deep discovery)
- [ ] Check logs confirm SDK usage for search, raw HTTP for Websets

**Implementation Note**: After completing this phase and automated verification passes, pause for manual confirmation before proceeding to Phase 3.

---

## Phase 3: New Exa Research Source

### Overview
Add a new event source using Exa SDK's `research.create_task()` for deeper research-based discovery.

### Changes Required:

#### 3.1 Add Exa Research Client

**File**: `api/services/exa_research.py` (NEW FILE)
**Changes**: Create new module for Exa Research API

```python
"""
Exa Research API client for deep event discovery.

Uses the SDK's research.create_task() for multi-step web research
that discovers events through comprehensive analysis.
"""

import logging
import os
from datetime import datetime
from typing import Any

from exa_py import Exa
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.services.exa_client import ExaSearchResult

logger = logging.getLogger(__name__)


class ExaResearchResult(BaseModel):
    """Result from Exa Research task."""

    task_id: str
    status: str  # "pending", "running", "completed", "failed"
    results: list[ExaSearchResult] | None = None
    summary: str | None = None


class ExaResearchClient:
    """
    Client for Exa Research API.

    Research tasks perform multi-step web research to find
    comprehensive information about a topic.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        self._client: Exa | None = None

    def _get_client(self) -> Exa:
        """Get or create the SDK client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("EXA_API_KEY not configured")
            self._client = Exa(api_key=self.api_key)
        return self._client

    def _sync_create_research_task(
        self,
        query: str,
        output_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Synchronous research task creation."""
        client = self._get_client()

        kwargs: dict[str, Any] = {}
        if output_schema:
            kwargs["output_schema"] = output_schema

        return client.research.create_task(query, **kwargs)

    async def create_research_task(
        self,
        query: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Create a research task for deep event discovery.

        Args:
            query: Research question/topic
            output_schema: Optional schema for structured output

        Returns:
            Task ID if created successfully
        """
        if not self.api_key:
            logger.warning("EXA_API_KEY not set")
            return None

        try:
            logger.debug("🔬 [Exa Research] Creating task | query=%s", query[:50])

            result = await run_in_threadpool(
                self._sync_create_research_task,
                query,
                output_schema,
            )

            task_id = getattr(result, 'id', None) or result.get('id') if isinstance(result, dict) else None
            if task_id:
                logger.debug("✅ [Exa Research] Task created | id=%s", task_id)
            return task_id

        except Exception as e:
            logger.warning("Exa research task creation error: %s", e)
            return None

    def _sync_get_task_status(self, task_id: str) -> Any:
        """Synchronous task status check."""
        client = self._get_client()
        return client.research.get_task(task_id)

    async def get_task_status(self, task_id: str) -> ExaResearchResult | None:
        """Get the status and results of a research task."""
        if not self.api_key:
            return None

        try:
            result = await run_in_threadpool(
                self._sync_get_task_status,
                task_id,
            )

            status = getattr(result, 'status', 'unknown')
            results = None

            if hasattr(result, 'results') and result.results:
                results = [
                    ExaSearchResult(
                        id=getattr(r, 'id', ''),
                        title=getattr(r, 'title', 'Untitled'),
                        url=getattr(r, 'url', ''),
                        text=getattr(r, 'text', None),
                    )
                    for r in result.results
                ]

            return ExaResearchResult(
                task_id=task_id,
                status=status,
                results=results,
                summary=getattr(result, 'summary', None),
            )

        except Exception as e:
            logger.warning("Exa research task status error: %s", e)
            return None


# Singleton instance
_research_client: ExaResearchClient | None = None


def get_exa_research_client() -> ExaResearchClient:
    """Get the singleton Exa Research client."""
    global _research_client
    if _research_client is None:
        _research_client = ExaResearchClient()
    return _research_client


async def research_events_adapter(profile: Any) -> list[ExaSearchResult]:
    """
    Adapter for registry pattern - uses Exa Research for deep discovery.

    NOTE: Research tasks are async and may take time. This adapter
    creates a task and polls for results (with timeout).
    """
    import asyncio

    client = get_exa_research_client()

    # Build research query
    query_parts = [
        "Find upcoming events in Columbus, Ohio",
        "Include dates, times, venues, and descriptions",
    ]

    if hasattr(profile, "categories") and profile.categories:
        query_parts.append(f"Focus on: {', '.join(profile.categories)}")

    if hasattr(profile, "keywords") and profile.keywords:
        query_parts.append(f"Related to: {', '.join(profile.keywords)}")

    query = ". ".join(query_parts)

    # Create research task
    task_id = await client.create_research_task(query)
    if not task_id:
        return []

    # Poll for results (max 60 seconds)
    max_polls = 12
    poll_interval = 5.0

    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)

        status = await client.get_task_status(task_id)
        if not status:
            continue

        if status.status == "completed":
            return status.results or []
        elif status.status == "failed":
            logger.warning("Exa research task %s failed", task_id)
            return []

    logger.warning("Exa research task %s timed out", task_id)
    return []


def register_exa_research_source() -> None:
    """Register Exa Research as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("EXA_API_KEY", "")

    source = EventSource(
        name="exa-research",
        search_fn=research_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=30,  # Lower priority - research is slower but deeper
        description="Exa Research API for deep event discovery",
    )
    register_event_source(source)
```

#### 3.2 Register New Source

**File**: `api/index.py`
**Changes**: Add registration call for Exa Research

```python
# Register event sources
register_eventbrite_source()
register_exa_source()
register_posh_source()
register_exa_research_source()  # NEW
```

#### 3.3 Update Exports

**File**: `api/services/__init__.py`
**Changes**: Export new module

```python
from api.services.exa_research import (
    ExaResearchClient,
    ExaResearchResult,
    get_exa_research_client,
    register_exa_research_source,
)
```

### Success Criteria:

#### Automated Verification:
- [x] Import check: `python -c "from api.services.exa_research import get_exa_research_client; print('OK')"`
- [x] All existing tests still pass
- [x] New source registers without errors

#### Manual Verification:
- [ ] Run search flow and verify Exa Research source appears in enabled sources
- [ ] If Exa Research API is accessible, verify it returns results

**Implementation Note**: Exa Research may have different API availability or rate limits. Test carefully in staging.

---

## Testing Strategy

### Unit Tests:
- Mock SDK clients for fast unit tests
- Test result conversion functions
- Test adapter filtering logic

### Integration Tests:
Update `api/services/tests/test_live_sources.py`:

```python
class TestExaClientLiveSDK:
    """Test Exa client using SDK."""

    @pytest.mark.integration
    async def test_search_basic(self, exa_client):
        """Test basic search via SDK."""
        results = await exa_client.search("tech events columbus ohio", num_results=5)
        # Empty results are acceptable
        assert isinstance(results, list)

    @pytest.mark.integration
    async def test_find_similar(self, exa_client):
        """Test find_similar via SDK."""
        results = await exa_client.find_similar("https://eventbrite.com")
        assert isinstance(results, list)


class TestFirecrawlClientLiveSDK:
    """Test Firecrawl client using SDK."""

    @pytest.mark.integration
    async def test_scrape_basic(self, firecrawl_client):
        """Test basic scrape via SDK."""
        result = await firecrawl_client.scrape("https://posh.vip", formats=["markdown"])
        assert isinstance(result, dict)
```

### Manual Testing Steps:
1. Start the API server locally
2. Send a chat message that triggers event search
3. Verify events from all sources appear
4. Check server logs for SDK usage (vs raw HTTP)
5. Test Websets by waiting for "more_events" SSE message

## Performance Considerations

- **Thread Pool Limit**: Default 40 concurrent threads for Exa SDK calls
- **Exa Research Timeout**: 60 seconds max polling time
- **Firecrawl is async**: No thread pool overhead
- **Websets remain async**: No change to background task performance

## Migration Notes

- No database changes required
- No breaking API changes
- Existing tests should pass with minimal updates
- Rollback: Revert to previous commit if issues arise

## References

- Research document: `thoughts/shared/research/2026-01-11-exa-firecrawl-sdk-migration.md`
- Exa SDK docs: https://docs.exa.ai/sdks/python-sdk-specification
- Firecrawl SDK docs: https://docs.firecrawl.dev/sdks/python
- FastAPI concurrency: https://fastapi.tiangolo.com/async/
