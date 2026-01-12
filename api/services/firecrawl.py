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

    async def close(self) -> None:
        """Close the client (no-op for SDK, kept for compatibility)."""
        # AsyncFirecrawl doesn't have a close method, but we keep this
        # for API compatibility
        self._client = None

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

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()

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

    async def _crawl_and_extract(
        self,
        discovery_url: str,
        limit: int = 20,
        include_patterns: list[str] | None = None,
    ) -> list[ScrapedEvent]:
        """
        Crawl a listing page and extract events.

        This is the core discovery logic that can be called by subclasses
        with platform-specific URLs and patterns.

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

        return await self._crawl_and_extract(
            discovery_url=city_url,
            limit=limit,
            include_patterns=["/e/*"],
        )


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
    import time

    extractor = get_posh_extractor()
    city = "columbus"  # TODO: Extract from profile.location

    # Extract time window for logging
    start_date = None
    end_date = None
    if hasattr(profile, "time_window") and profile.time_window:
        start_date = profile.time_window.start
        end_date = profile.time_window.end

    # Log the outbound query
    logger.debug(
        "📤 [Posh] Outbound Query | city='%s' start=%s end=%s free_only=%s",
        city,
        start_date,
        end_date,
        getattr(profile, "free_only", False),
    )

    start_time = time.perf_counter()
    events = await extractor.discover_events(city=city, limit=30)
    fetch_elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [Posh] Fetched | events=%d duration=%.2fs",
        len(events),
        fetch_elapsed,
    )

    # Post-fetch filtering
    filtered_events = []
    filtered_out_time = 0
    filtered_out_price = 0

    for event in events:
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    filtered_out_time += 1
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    filtered_out_time += 1
                    continue

        if hasattr(profile, "free_only") and profile.free_only:
            if not event.is_free:
                filtered_out_price += 1
                continue

        filtered_events.append(event)

    # Log filtering results
    if filtered_out_time > 0 or filtered_out_price > 0:
        logger.debug(
            "🔍 [Posh] Filtered | kept=%d removed_time=%d removed_price=%d",
            len(filtered_events),
            filtered_out_time,
            filtered_out_price,
        )

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
