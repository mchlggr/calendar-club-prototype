"""
Firecrawl-based web scraping for event discovery.

Provides extractors for various event platforms using Firecrawl's
structured extraction capabilities.
"""

import logging
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Firecrawl API configuration
FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1"


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
    Async client for Firecrawl API.

    Firecrawl provides web scraping with LLM-based extraction.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError("FIRECRAWL_API_KEY not configured")
            self._client = httpx.AsyncClient(
                base_url=FIRECRAWL_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
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
            formats: Output formats (e.g., ["markdown", "html", "extract"])
            extract_schema: JSON schema for structured extraction

        Returns:
            Scraped content with requested formats
        """
        client = await self._get_client()

        payload: dict[str, Any] = {"url": url}
        if formats:
            payload["formats"] = formats
        if extract_schema:
            payload["extract"] = {"schema": extract_schema}

        response = await client.post("/scrape", json=payload)
        response.raise_for_status()

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"Scrape failed: {data.get('error', 'Unknown error')}")

        return data.get("data", {})

    async def crawl(
        self,
        url: str,
        max_depth: int = 2,
        limit: int = 10,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Crawl a website starting from the given URL.

        Args:
            url: Starting URL
            max_depth: Maximum crawl depth
            limit: Maximum number of pages to crawl
            include_patterns: URL patterns to include
            exclude_patterns: URL patterns to exclude

        Returns:
            List of scraped page data
        """
        client = await self._get_client()

        payload: dict[str, Any] = {
            "url": url,
            "maxDepth": max_depth,
            "limit": limit,
        }
        if include_patterns:
            payload["includePaths"] = include_patterns
        if exclude_patterns:
            payload["excludePaths"] = exclude_patterns

        response = await client.post("/crawl", json=payload)
        response.raise_for_status()

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"Crawl failed: {data.get('error', 'Unknown error')}")

        return data.get("data", [])


class PoshExtractor:
    """
    Extractor for Posh (posh.vip) events.

    Posh is a social events platform popular for nightlife,
    parties, and social gatherings.
    """

    SOURCE_NAME = "posh"
    BASE_URL = "https://posh.vip"

    # Schema for extracting event data from Posh pages
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

    def __init__(self, client: FirecrawlClient | None = None):
        self.client = client or FirecrawlClient()

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()

    def _extract_event_id(self, url: str) -> str:
        """Extract event ID from Posh URL."""
        # Posh URLs are typically: https://posh.vip/e/event-slug-123abc
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if path.startswith("e/"):
            return path[2:]  # Remove 'e/' prefix
        return path or url

    def _parse_datetime(
        self, date_str: str | None, time_str: str | None
    ) -> tuple[datetime | None, datetime | None]:
        """Parse Posh date/time strings into datetime objects."""
        if not date_str:
            return None, None

        try:
            import dateparser

            # Combine date and time for parsing
            combined = date_str
            if time_str:
                # Extract start time (before any dash or "to")
                time_parts = re.split(r"\s*[-–to]\s*", time_str, maxsplit=1)
                start_time = time_parts[0].strip()
                combined = f"{date_str} {start_time}"

            start_dt = dateparser.parse(
                combined,
                settings={"PREFER_DATES_FROM": "future"},
            )

            # Parse end time if available
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

        # Extract numeric price
        match = re.search(r"\$?(\d+(?:\.\d{2})?)", price_str)
        if match:
            price = float(match.group(1))
            return False, int(price * 100)  # Store in cents

        return True, None

    async def extract_event(self, url: str) -> ScrapedEvent | None:
        """
        Extract event data from a Posh event page.

        Args:
            url: Posh event URL

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
                logger.warning("No title found in Posh event: %s", url)
                return None

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
                category="nightlife",  # Posh is primarily nightlife/social
                is_free=is_free,
                price_amount=price_amount,
                url=url,
                logo_url=extracted.get("image_url"),
                raw_data=extracted,
            )

        except Exception as e:
            logger.error("Failed to extract Posh event from %s: %s", url, e)
            return None

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
        try:
            # Crawl the city's event listing page
            city_url = urljoin(self.BASE_URL, f"/c/{city}")

            pages = await self.client.crawl(
                url=city_url,
                max_depth=1,
                limit=limit + 5,  # Get extra in case some fail
                include_patterns=["/e/*"],  # Only event pages
            )

            events = []
            for page in pages:
                url = page.get("url", "")
                if "/e/" not in url:
                    continue

                event = await self.extract_event(url)
                if event:
                    events.append(event)
                    if len(events) >= limit:
                        break

            logger.info("Discovered %d Posh events for %s", len(events), city)
            return events

        except Exception as e:
            logger.error("Failed to discover Posh events for %s: %s", city, e)
            return []


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


# Aliases for backward compatibility
LumaEvent = ScrapedEvent
LumaExtractor = PoshExtractor

