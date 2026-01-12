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
    extracted_event: dict[str, Any] | None = None  # LLM-extracted event data


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

    async def _extract_event_from_text(
        self,
        title: str,
        text: str | None,
        highlights: list[str] | None,
        url: str,
    ) -> dict[str, Any] | None:
        """
        Use lightweight LLM to extract event details from search result text.

        Returns dict with: title, start_date, start_time, venue_name, price, description
        """
        if not text and not highlights:
            return None

        # Combine text sources
        content = ""
        if highlights:
            content = " ".join(highlights[:3])
        if text and len(content) < 500:
            content += " " + text[:500]

        if len(content.strip()) < 50:
            return None  # Not enough content to extract from

        try:
            import json

            from openai import AsyncOpenAI

            client = AsyncOpenAI()

            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # Lightweight model for cost/speed
                messages=[
                    {
                        "role": "system",
                        "content": """Extract event details from the text. Return JSON with:
- title: Event name
- start_date: Date as 'Month Day, Year' (e.g., 'January 15, 2026'). MUST include year.
- start_time: Time with AM/PM if found, else null
- venue_name: Venue name if found, 'Online' for virtual, else null
- price: 'Free' or '$XX' format, else null
- description: One sentence summary

If this is NOT an event page or details cannot be extracted, return {"is_event": false}.""",
                    },
                    {
                        "role": "user",
                        "content": f"Page title: {title}\n\nContent: {content[:1000]}",
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
                temperature=0,
            )

            result = response.choices[0].message.content
            if result:
                data = json.loads(result)
                if data.get("is_event") is False:
                    return None
                return data

        except Exception as e:
            logger.debug("Event extraction failed for %s: %s", url, e)

        return None

    async def _enrich_with_extraction(
        self,
        results: list[ExaSearchResult],
    ) -> list[ExaSearchResult]:
        """Enrich search results with LLM-extracted event details."""
        import asyncio

        async def extract_one(result: ExaSearchResult) -> ExaSearchResult:
            extracted = await self._extract_event_from_text(
                result.title,
                result.text,
                result.highlights,
                result.url,
            )
            if extracted:
                # Create a new result with extracted_event set
                return ExaSearchResult(
                    id=result.id,
                    title=result.title,
                    url=result.url,
                    score=result.score,
                    published_date=result.published_date,
                    author=result.author,
                    text=result.text,
                    highlights=result.highlights,
                    extracted_event=extracted,
                )
            return result

        # Run extractions in parallel (batch of 5 at a time to avoid rate limits)
        enriched = []
        for i in range(0, len(results), 5):
            batch = results[i : i + 5]
            batch_results = await asyncio.gather(*[extract_one(r) for r in batch])
            enriched.extend(batch_results)

        return enriched

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
        extract_events: bool = False,
    ) -> list[ExaSearchResult]:
        """
        Search the web using Exa's neural search.

        Uses SDK wrapped in thread pool for async compatibility.

        Args:
            extract_events: If True, use LLM to extract structured event data
                           from each result's text content
        """
        if not self.api_key:
            logger.warning("EXA_API_KEY not set, returning empty results")
            return []

        try:
            logger.debug(
                "🌐 [Exa] Starting search | query=%s num_results=%d extract=%s",
                query[:50],
                num_results,
                extract_events,
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

            # Optionally extract event details from text
            if extract_events and results:
                results = await self._enrich_with_extraction(results)

            elapsed = time.perf_counter() - start_time
            if results:
                extracted_count = sum(1 for r in results if r.extracted_event)
                logger.debug(
                    "✅ [Exa] Complete | results=%d extracted=%d duration=%.2fs",
                    len(results),
                    extracted_count,
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


# Singleton instance
_client: ExaClient | None = None


def get_exa_client() -> ExaClient:
    """Get the singleton Exa client."""
    global _client
    if _client is None:
        _client = ExaClient()
    return _client


def _format_date_range_for_query(time_window: Any) -> str:
    """
    Format a time window as natural language for neural search.

    Examples:
        - "happening January 15-20, 2026"
        - "happening January 15, 2026"
        - "happening in January 2026"
    """
    if not time_window:
        return ""

    start = time_window.start
    end = time_window.end

    if not start:
        return ""

    # Format depends on whether we have a range or single date
    if end and start.date() != end.date():
        # Date range
        if start.month == end.month and start.year == end.year:
            # Same month: "January 15-20, 2026"
            return f"happening {start.strftime('%B')} {start.day}-{end.day}, {start.year}"
        else:
            # Different months: "January 15 - February 2, 2026"
            return f"happening {start.strftime('%B %d')} - {end.strftime('%B %d, %Y')}"
    else:
        # Single date or same day: "January 15, 2026"
        return f"happening {start.strftime('%B %d, %Y')}"


async def search_events_adapter(profile: Any) -> list[ExaSearchResult]:
    """
    Adapter for registry pattern - searches Exa using a SearchProfile.

    Uses natural language query construction for Exa's neural search.
    Date ranges are included IN the query text (not as API filters) because
    Exa's date filters are for page publication date, not event date.

    We DO add a 6-month recency filter for page publication to avoid stale results.

    Args:
        profile: SearchProfile with search criteria

    Returns:
        List of ExaSearchResult objects
    """
    from datetime import timedelta

    client = get_exa_client()

    # Calculate publication date range: 6 months ago to today
    # This filters for recently published pages (not event dates)
    today = datetime.now()
    six_months_ago = today - timedelta(days=180)

    # Build search query with natural language for neural search
    query_parts = []

    # Add event type and location context
    query_parts.append("events in Columbus, Ohio")

    # Add date range as natural language (CRITICAL for grounding)
    if hasattr(profile, "time_window") and profile.time_window:
        date_text = _format_date_range_for_query(profile.time_window)
        if date_text:
            query_parts.append(date_text)

    # Add categories
    if hasattr(profile, "categories") and profile.categories:
        query_parts.extend(profile.categories)

    # Add keywords
    if hasattr(profile, "keywords") and profile.keywords:
        query_parts.extend(profile.keywords)

    query = " ".join(query_parts)

    # Log the complete outbound query for debugging
    logger.debug(
        "📤 [Exa] Outbound Query | query='%s' num_results=%d",
        query,
        100,
    )

    # NOTE: start_published_date/end_published_date filter by when a PAGE was published,
    # not when an EVENT occurs. We use a 6-month recency filter to avoid stale pages.

    return await client.search(
        query=query,
        num_results=100,
        include_text=True,
        include_highlights=True,
        extract_events=True,  # Enable LLM extraction for structured event data
        start_published_date=six_months_ago,  # Filter out pages older than 6 months
        end_published_date=today,
    )


def register_exa_source() -> None:
    """Register Exa as an event source in the global registry."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("EXA_API_KEY", "")

    source = EventSource(
        name="exa",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=20,  # Lower priority than Eventbrite - less structured data
        description="Exa neural web search for event discovery",
    )
    register_event_source(source)
