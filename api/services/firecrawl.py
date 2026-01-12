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


# Unified extraction schema for all Firecrawl extractors.
# Field descriptions guide Firecrawl's LLM for accurate extraction.
BASE_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Event title - the main headline or name of the event",
        },
        "description": {
            "type": ["string", "null"],
            "description": (
                "Event description or summary. First 1000 characters if very long. "
                "Return null if no description found."
            ),
        },
        "start_date": {
            "type": "string",
            "description": (
                "Event start date in format 'Month Day, Year' (e.g., 'January 15, 2026'). "
                "MUST include the full year - infer from context if not displayed on page. "
                "Never return relative dates like 'tomorrow' or 'next week'."
            ),
        },
        "start_time": {
            "type": ["string", "null"],
            "description": (
                "Event start time with AM/PM (e.g., '7:00 PM', '10:30 AM'). "
                "Include timezone abbreviation if shown on page (e.g., 'EST', 'PT'). "
                "Return null if time not specified."
            ),
        },
        "end_time": {
            "type": ["string", "null"],
            "description": (
                "Event end time with AM/PM. Same format as start_time. "
                "Return null if not specified."
            ),
        },
        "venue_name": {
            "type": ["string", "null"],
            "description": (
                "Venue or location name. Return 'Online' for virtual/remote events. "
                "Return null if not specified or marked as TBA."
            ),
        },
        "venue_address": {
            "type": ["string", "null"],
            "description": (
                "Full street address including city, state/region, and zip/postal code "
                "if available. Return null for online events or if address not disclosed."
            ),
        },
        "price": {
            "type": "string",
            "description": (
                "Entry/ticket price. Return 'Free' if: event is free, RSVP-only, "
                "donation-based, or no price is shown. For paid events return price "
                "with currency symbol (e.g., '$25'). For price ranges use '$10-50' format. "
                "If multiple ticket tiers, return the lowest price."
            ),
        },
        "image_url": {
            "type": ["string", "null"],
            "description": (
                "URL of the main event banner or cover image. Must be a full URL "
                "starting with https://. Do NOT return: logos, profile pictures, "
                "sponsor images, or advertisement banners. Return null if no "
                "event-specific image found."
            ),
        },
        "organizer": {
            "type": ["string", "null"],
            "description": (
                "Name of the event organizer, host, or hosting organization. "
                "Return null if not specified."
            ),
        },
    },
    "required": ["title", "start_date"],
}


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
    EVENT_SCHEMA: dict[str, Any] = BASE_EVENT_SCHEMA
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

    def _parse_datetime_from_schema(
        self,
        start_date: str | None,
        start_time: str | None,
        end_time: str | None,
    ) -> tuple[datetime | None, datetime | None]:
        """
        Parse date/time strings from BASE_EVENT_SCHEMA into datetime objects.

        This method handles the standardized format where:
        - start_date: 'Month Day, Year' (e.g., 'January 15, 2026')
        - start_time: 'H:MM AM/PM [TZ]' (e.g., '7:00 PM EST')
        - end_time: Same format as start_time
        """
        if not start_date:
            return None, None

        try:
            import dateparser
            from datetime import timedelta

            # Combine date and start time
            combined = start_date
            if start_time:
                # Remove timezone abbreviation for parsing (dateparser handles it)
                combined = f"{start_date} {start_time}"

            start_dt = dateparser.parse(
                combined,
                settings={"PREFER_DATES_FROM": "future"},
            )

            # Parse end time if provided
            end_dt = None
            if end_time and start_dt:
                end_combined = f"{start_date} {end_time}"
                end_dt = dateparser.parse(
                    end_combined,
                    settings={"PREFER_DATES_FROM": "future"},
                )
                # Handle overnight events (end time before start time)
                if end_dt and start_dt and end_dt < start_dt:
                    end_dt = end_dt + timedelta(days=1)

            return start_dt, end_dt

        except Exception as e:
            logger.warning(
                "Failed to parse datetime: date=%s start=%s end=%s error=%s",
                start_date,
                start_time,
                end_time,
                e,
            )
            return None, None

    def _parse_price_from_schema(self, price_str: str | None) -> tuple[bool, int | None]:
        """
        Parse price string from BASE_EVENT_SCHEMA into (is_free, price_cents).

        Handles: 'Free', '$25', '$10-50', '$15+'
        """
        if not price_str:
            return True, None

        price_lower = price_str.lower().strip()
        if price_lower in ("free", "no cover", "complimentary", "donation", "rsvp", ""):
            return True, None

        # Extract first number from price string
        match = re.search(r"\$?(\d+(?:\.\d{2})?)", price_str)
        if match:
            price = float(match.group(1))
            return False, int(price * 100)  # Convert to cents

        return True, None

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
    # Uses BASE_EVENT_SCHEMA from parent class

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Posh URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path.startswith("e/"):
            return path[2:]
        return path or url

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Posh extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )
        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted["title"],
            description=extracted.get("description") or "",
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


class LumaExtractor(BaseExtractor):
    """
    Extractor for Luma (luma.com) events.

    Luma is a modern event platform popular for tech meetups,
    conferences, and community gatherings.
    """

    SOURCE_NAME = "luma"
    BASE_URL = "https://lu.ma"
    DEFAULT_CATEGORY = "tech"
    # Uses BASE_EVENT_SCHEMA from parent class

    # City slugs supported by Luma
    CITY_SLUGS = {
        "columbus": "columbus",  # May not exist - will gracefully fail
        "new york": "nyc",
        "san francisco": "sf",
        "los angeles": "la",
        "chicago": "chicago",
        "boston": "boston",
        "austin": "austin",
        "seattle": "seattle",
        "denver": "denver",
        "miami": "miami",
        "atlanta": "atlanta",
        "toronto": "toronto",
        "london": "london",
        "berlin": "berlin",
    }

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Luma URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        # Luma URLs are like /eventslug or /abc123xy
        return path or url

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Luma extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )
        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted.get("title", "Untitled"),
            description=extracted.get("description") or "",
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
        city: str = "sf",
        limit: int = 20,
    ) -> list[ScrapedEvent]:
        """
        Discover Luma events for a city.

        Args:
            city: City slug (e.g., 'sf', 'nyc', 'austin')
            limit: Maximum number of events to return

        Returns:
            List of discovered events
        """
        # Normalize city to Luma slug
        city_slug = self.CITY_SLUGS.get(city.lower(), city.lower())
        discovery_url = f"{self.BASE_URL}/{city_slug}"

        logger.info("Discovering Luma events for %s at %s", city, discovery_url)

        # Luma event links have various patterns, scrape the page and extract
        try:
            # First, get all links from the city page
            data = await self.client.scrape(
                url=discovery_url,
                formats=["links", "markdown"],
            )

            links = data.get("links", [])

            # Filter to event links (exclude static pages)
            event_urls = []
            static_paths = {"/discover", "/about", "/pricing", "/login", "/signup", "/help"}
            for link in links:
                href = link if isinstance(link, str) else link.get("href", "")
                if not href:
                    continue
                parsed = urlparse(href)
                path = parsed.path.strip("/")
                # Luma event URLs are short slugs or 8-char codes
                if (
                    path
                    and "/" not in path  # No nested paths
                    and path not in static_paths
                    and not path.startswith(("discover", "about", "help"))
                    and len(path) <= 50  # Reasonable slug length
                ):
                    full_url = f"{self.BASE_URL}/{path}"
                    if full_url not in event_urls:
                        event_urls.append(full_url)

            logger.info("Found %d potential Luma event URLs", len(event_urls))

            # Extract events from URLs
            events = []
            for url in event_urls[:limit + 5]:  # Buffer for failures
                event = await self.extract_event(url)
                if event:
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d Luma events", len(events))
            return events

        except Exception as e:
            logger.error("Failed to discover Luma events: %s", e)
            return []


# Singleton for LumaExtractor
_luma_extractor: LumaExtractor | None = None


def get_luma_extractor() -> LumaExtractor:
    """Get the singleton Luma extractor."""
    global _luma_extractor
    if _luma_extractor is None:
        _luma_extractor = LumaExtractor()
    return _luma_extractor


async def search_luma_adapter(profile: Any) -> list[ScrapedEvent]:
    """Adapter for registry pattern - searches Luma events."""
    import time

    extractor = get_luma_extractor()

    # TODO: Extract city from profile.location when available
    city = "sf"  # Default to SF for now

    # Log the outbound query
    logger.debug(
        "📤 [Luma] Outbound Query | city='%s'",
        city,
    )

    start_time = time.perf_counter()
    events = await extractor.discover_events(city=city, limit=20)
    fetch_elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [Luma] Fetched | events=%d duration=%.2fs",
        len(events),
        fetch_elapsed,
    )

    # Post-filter by time window if provided
    filtered = []
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

        filtered.append(event)

    return filtered


def register_luma_source() -> None:
    """Register Luma as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="luma",
        search_fn=search_luma_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=26,
        description="Luma events via Firecrawl scraping",
    )
    register_event_source(source)


class PartifulExtractor(BaseExtractor):
    """
    Extractor for Partiful (partiful.com) events.

    Partiful is a social events platform popular for parties,
    gatherings, and community events.
    """

    SOURCE_NAME = "partiful"
    BASE_URL = "https://partiful.com"
    DEFAULT_CATEGORY = "social"
    # Uses BASE_EVENT_SCHEMA from parent class

    # City codes supported by Partiful
    CITY_CODES = {
        "new york": "nyc",
        "los angeles": "la",
        "san francisco": "sf",
        "boston": "bos",
        "washington dc": "dc",
        "chicago": "chi",
        "miami": "mia",
        "london": "lon",
    }

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Partiful URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        # Partiful URLs are like /e/abc123xyz
        if path.startswith("e/"):
            return path[2:]
        return path or url

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Partiful extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )
        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted.get("title", "Untitled"),
            description=extracted.get("description") or "",
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
        city: str = "nyc",
        limit: int = 20,
    ) -> list[ScrapedEvent]:
        """
        Discover Partiful events for a city.

        Args:
            city: City code (e.g., 'nyc', 'sf', 'la')
            limit: Maximum number of events to return

        Returns:
            List of discovered events
        """
        # Normalize city to Partiful code
        city_code = self.CITY_CODES.get(city.lower(), city.lower())
        discovery_url = f"{self.BASE_URL}/discover/{city_code}"

        logger.info("Discovering Partiful events for %s at %s", city, discovery_url)

        try:
            # Get links from discovery page
            data = await self.client.scrape(
                url=discovery_url,
                formats=["links", "markdown"],
            )

            links = data.get("links", [])

            # Filter to event links (/e/...)
            event_urls = []
            for link in links:
                href = link if isinstance(link, str) else link.get("href", "")
                if not href:
                    continue
                if "/e/" in href:
                    # Ensure full URL
                    if href.startswith("/"):
                        href = f"{self.BASE_URL}{href}"
                    elif not href.startswith("http"):
                        href = f"{self.BASE_URL}/{href}"
                    if href not in event_urls:
                        event_urls.append(href)

            logger.info("Found %d Partiful event URLs", len(event_urls))

            # Extract events
            events = []
            for url in event_urls[:limit + 5]:
                event = await self.extract_event(url)
                if event:
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d Partiful events", len(events))
            return events

        except Exception as e:
            logger.error("Failed to discover Partiful events: %s", e)
            return []


# Singleton for PartifulExtractor
_partiful_extractor: PartifulExtractor | None = None


def get_partiful_extractor() -> PartifulExtractor:
    """Get the singleton Partiful extractor."""
    global _partiful_extractor
    if _partiful_extractor is None:
        _partiful_extractor = PartifulExtractor()
    return _partiful_extractor


async def search_partiful_adapter(profile: Any) -> list[ScrapedEvent]:
    """Adapter for registry pattern - searches Partiful events."""
    import time

    extractor = get_partiful_extractor()
    city = "nyc"  # Default

    logger.debug("📤 [Partiful] Outbound Query | city='%s'", city)

    start_time = time.perf_counter()
    events = await extractor.discover_events(city=city, limit=20)
    fetch_elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [Partiful] Fetched | events=%d duration=%.2fs",
        len(events),
        fetch_elapsed,
    )

    # Post-filter
    filtered = []
    for event in events:
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    continue
        filtered.append(event)

    return filtered


def register_partiful_source() -> None:
    """Register Partiful as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="partiful",
        search_fn=search_partiful_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=27,
        description="Partiful social events via Firecrawl scraping",
    )
    register_event_source(source)


class MeetupExtractor(BaseExtractor):
    """
    Extractor for Meetup (meetup.com) events via Firecrawl scraping.

    Scrapes public event listings from meetup.com/find/ pages.
    """

    SOURCE_NAME = "meetup"
    BASE_URL = "https://www.meetup.com"
    DEFAULT_CATEGORY = "community"
    # Uses BASE_EVENT_SCHEMA from parent class

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Meetup URL."""
        # URL like /group-name/events/12345/
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if "events" in parts:
            idx = parts.index("events")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return parsed.path

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Meetup extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )

        # Check if online - skip online events
        venue_name = extracted.get("venue_name", "")
        if venue_name and venue_name.lower() == "online":
            return None

        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted.get("title", "Untitled"),
            description=extracted.get("description") or "",
            start_time=start_dt,
            end_time=end_dt,
            venue_name=venue_name or None,
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
        location: str = "Columbus, OH",
        limit: int = 20,
    ) -> list[ScrapedEvent]:
        """Discover Meetup events for a location."""
        from urllib.parse import quote_plus

        encoded_location = quote_plus(location)
        discovery_url = f"{self.BASE_URL}/find/?location={encoded_location}&eventType=inPerson"

        logger.info("Discovering Meetup events at %s", discovery_url)

        try:
            data = await self.client.scrape(
                url=discovery_url,
                formats=["links", "markdown"],
            )

            links = data.get("links", [])

            # Filter to event links
            event_urls = []
            for link in links:
                href = link if isinstance(link, str) else link.get("href", "")
                if "/events/" in href and href not in event_urls:
                    if not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"
                    event_urls.append(href)

            logger.info("Found %d Meetup event URLs", len(event_urls))

            events = []
            for url in event_urls[:limit + 5]:
                event = await self.extract_event(url)
                if event:
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d Meetup events", len(events))
            return events

        except Exception as e:
            logger.error("Failed to discover Meetup events: %s", e)
            return []


# Singleton for MeetupExtractor
_meetup_extractor: MeetupExtractor | None = None


def get_meetup_extractor() -> MeetupExtractor:
    """Get the singleton Meetup extractor."""
    global _meetup_extractor
    if _meetup_extractor is None:
        _meetup_extractor = MeetupExtractor()
    return _meetup_extractor


async def search_meetup_adapter(profile: Any) -> list[ScrapedEvent]:
    """Adapter for registry pattern - searches Meetup events."""
    import time

    extractor = get_meetup_extractor()
    location = "Columbus, OH"  # Default

    logger.debug("📤 [Meetup] Outbound Query | location='%s'", location)

    start_time = time.perf_counter()
    events = await extractor.discover_events(location=location, limit=20)
    fetch_elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [Meetup] Fetched | events=%d duration=%.2fs",
        len(events),
        fetch_elapsed,
    )

    # Post-filter
    filtered = []
    for event in events:
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    continue
        filtered.append(event)

    return filtered


def register_meetup_scraper_source() -> None:
    """Register Meetup scraper as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="meetup_scraper",
        search_fn=search_meetup_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=28,
        description="Meetup events via Firecrawl scraping",
    )
    register_event_source(source)


class FacebookExtractor(BaseExtractor):
    """
    Extractor for Facebook Events via scraping.

    Scrapes public events from facebook.com/events/search.
    Firecrawl handles anti-bot measures on their infrastructure.
    """

    SOURCE_NAME = "facebook"
    BASE_URL = "https://www.facebook.com"
    DEFAULT_CATEGORY = "community"
    # Uses BASE_EVENT_SCHEMA from parent class

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Facebook URL."""
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if "events" in parts:
            idx = parts.index("events")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return parsed.path

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse Facebook extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )
        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted.get("title", "Untitled"),
            description=extracted.get("description") or "",
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
        query: str = "Columbus",
        limit: int = 20,
    ) -> list[ScrapedEvent]:
        """Discover Facebook events by search query."""
        from urllib.parse import quote_plus

        encoded_query = quote_plus(query)
        discovery_url = f"{self.BASE_URL}/events/search/?q={encoded_query}"

        logger.info("Discovering Facebook events at %s", discovery_url)

        try:
            data = await self.client.scrape(
                url=discovery_url,
                formats=["links", "markdown"],
            )

            links = data.get("links", [])

            event_urls = []
            for link in links:
                href = link if isinstance(link, str) else link.get("href", "")
                # Facebook event URLs contain /events/ followed by numeric ID
                if "/events/" in href and any(c.isdigit() for c in href):
                    if not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"
                    # Remove tracking params
                    parsed = urlparse(href)
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if clean_url not in event_urls:
                        event_urls.append(clean_url)

            logger.info("Found %d Facebook event URLs", len(event_urls))

            events = []
            for url in event_urls[:limit + 5]:
                event = await self.extract_event(url)
                if event:
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d Facebook events", len(events))
            return events

        except Exception as e:
            logger.error("Failed to discover Facebook events: %s", e)
            return []


# Singleton for FacebookExtractor
_facebook_extractor: FacebookExtractor | None = None


def get_facebook_extractor() -> FacebookExtractor:
    """Get the singleton Facebook extractor."""
    global _facebook_extractor
    if _facebook_extractor is None:
        _facebook_extractor = FacebookExtractor()
    return _facebook_extractor


async def search_facebook_adapter(profile: Any) -> list[ScrapedEvent]:
    """Adapter for registry pattern - searches Facebook events."""
    import time

    extractor = get_facebook_extractor()
    query = "Columbus"  # Default

    logger.debug("📤 [Facebook] Outbound Query | query='%s'", query)

    start_time = time.perf_counter()
    events = await extractor.discover_events(query=query, limit=20)
    fetch_elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [Facebook] Fetched | events=%d duration=%.2fs",
        len(events),
        fetch_elapsed,
    )

    # Post-filter
    filtered = []
    for event in events:
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    continue
        filtered.append(event)

    return filtered


def register_facebook_source() -> None:
    """Register Facebook as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="facebook",
        search_fn=search_facebook_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=29,
        description="Facebook events via Firecrawl scraping",
    )
    register_event_source(source)


class RiverExtractor(BaseExtractor):
    """
    Extractor for River (getriver.io) community events.

    River organizes events by community (e.g., All-In Podcast, MFM).
    We scrape the discovery page and filter by city from venue data.
    """

    SOURCE_NAME = "river"
    BASE_URL = "https://app.getriver.io"
    DEFAULT_CATEGORY = "community"
    # Uses BASE_EVENT_SCHEMA from parent class

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from River URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path.startswith("events/"):
            return path[7:]  # Remove 'events/'
        return path

    def _parse_extracted_data(
        self,
        url: str,
        extracted: dict[str, Any],
    ) -> ScrapedEvent | None:
        """Parse River extracted data into ScrapedEvent."""
        start_dt, end_dt = self._parse_datetime_from_schema(
            extracted.get("start_date"),
            extracted.get("start_time"),
            extracted.get("end_time"),
        )
        is_free, price_amount = self._parse_price_from_schema(extracted.get("price"))

        return ScrapedEvent(
            source=self.SOURCE_NAME,
            event_id=self._extract_event_id(url),
            title=extracted.get("title", "Untitled"),
            description=extracted.get("description") or "",
            start_time=start_dt,
            end_time=end_dt,
            venue_name=extracted.get("venue_name") or extracted.get("organizer"),
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
        city_filter: str | None = None,
        limit: int = 20,
    ) -> list[ScrapedEvent]:
        """
        Discover River events.

        Args:
            city_filter: Optional city to filter by (from venue address)
            limit: Maximum number of events

        Returns:
            List of events (filtered by city if specified)
        """
        discovery_url = f"{self.BASE_URL}/discovery/communities"

        logger.info("Discovering River events at %s", discovery_url)

        try:
            data = await self.client.scrape(
                url=discovery_url,
                formats=["links", "markdown"],
            )

            links = data.get("links", [])

            # River event URLs contain /events/
            event_urls = []
            for link in links:
                href = link if isinstance(link, str) else link.get("href", "")
                if "/events/" in href:
                    if not href.startswith("http"):
                        href = f"{self.BASE_URL}{href}"
                    if href not in event_urls:
                        event_urls.append(href)

            logger.info("Found %d River event URLs", len(event_urls))

            events = []
            for url in event_urls[:limit + 10]:
                event = await self.extract_event(url)
                if event:
                    # Filter by city if specified
                    if city_filter:
                        location = (event.venue_address or "").lower()
                        if city_filter.lower() not in location:
                            continue
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d River events", len(events))
            return events

        except Exception as e:
            logger.error("Failed to discover River events: %s", e)
            return []


# Singleton for RiverExtractor
_river_extractor: RiverExtractor | None = None


def get_river_extractor() -> RiverExtractor:
    """Get the singleton River extractor."""
    global _river_extractor
    if _river_extractor is None:
        _river_extractor = RiverExtractor()
    return _river_extractor


async def search_river_adapter(profile: Any) -> list[ScrapedEvent]:
    """Adapter for registry pattern - searches River events."""
    import time

    extractor = get_river_extractor()
    city_filter = None  # No filter by default

    logger.debug("📤 [River] Outbound Query | city_filter='%s'", city_filter)

    start_time = time.perf_counter()
    events = await extractor.discover_events(city_filter=city_filter, limit=20)
    fetch_elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [River] Fetched | events=%d duration=%.2fs",
        len(events),
        fetch_elapsed,
    )

    # Post-filter
    filtered = []
    for event in events:
        if hasattr(profile, "time_window") and profile.time_window:
            if profile.time_window.start and event.start_time:
                if event.start_time < profile.time_window.start:
                    continue
            if profile.time_window.end and event.start_time:
                if event.start_time > profile.time_window.end:
                    continue
        filtered.append(event)

    return filtered


def register_river_source() -> None:
    """Register River as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="river",
        search_fn=search_river_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=30,
        description="River community events via Firecrawl scraping",
    )
    register_event_source(source)


# Backward compatibility alias
LumaEvent = ScrapedEvent
