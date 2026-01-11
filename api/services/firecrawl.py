"""
Firecrawl client for web scraping and Luma event extraction.

Uses the Firecrawl API to scrape web pages and extract structured data.
Includes specialized extractor for Luma (lu.ma) event pages.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class LumaEvent(BaseModel):
    """Parsed event from a Luma page."""

    id: str = Field(description="Event ID extracted from URL")
    title: str
    description: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    host_name: str | None = None
    is_online: bool = False
    url: str
    cover_image_url: str | None = None
    ticket_price: str | None = None  # "Free" or "$X"


class ScrapeResult(BaseModel):
    """Result from a Firecrawl scrape operation."""

    markdown: str | None = None
    html: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class FirecrawlClient:
    """Async client for Firecrawl API.

    Provides methods to scrape web pages and return content in
    formats suitable for LLM processing.
    """

    API_BASE_URL = "https://api.firecrawl.dev/v1"

    def __init__(self, api_key: str):
        """Initialize the Firecrawl client.

        Args:
            api_key: Firecrawl API key (fc-...)
        """
        self.api_key = api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.API_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,  # Scraping can take a while
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
        wait_for: int | None = None,
    ) -> ScrapeResult:
        """Scrape a single URL.

        Args:
            url: The URL to scrape
            formats: Output formats to request (default: ["markdown"])
            wait_for: Milliseconds to wait for page to load (for JS-heavy pages)

        Returns:
            ScrapeResult with markdown/html content and metadata
        """
        if formats is None:
            formats = ["markdown"]

        client = await self._get_client()

        payload: dict[str, Any] = {
            "url": url,
            "formats": formats,
        }

        if wait_for:
            payload["waitFor"] = wait_for

        try:
            response = await client.post("/scrape", json=payload)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                error_msg = data.get("error", "Unknown scrape error")
                logger.warning("Firecrawl scrape failed for %s: %s", url, error_msg)
                return ScrapeResult(success=False, error=error_msg)

            result_data = data.get("data", {})
            return ScrapeResult(
                markdown=result_data.get("markdown"),
                html=result_data.get("html"),
                metadata=result_data.get("metadata", {}),
                success=True,
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.error("Firecrawl HTTP error for %s: %s", url, error_msg)
            return ScrapeResult(success=False, error=error_msg)
        except httpx.HTTPError as e:
            logger.error("Firecrawl request error for %s: %s", url, e)
            return ScrapeResult(success=False, error=str(e))


class LumaExtractor:
    """Extracts structured event data from Luma (lu.ma) pages.

    Luma pages contain JSON-LD structured data and predictable HTML patterns
    that we can parse to extract event information.
    """

    # Pattern to match lu.ma or luma.com event URLs
    URL_PATTERN = re.compile(
        r"https?://(?:lu\.ma|luma\.com)/(?P<event_id>[a-zA-Z0-9_-]+)"
    )

    @classmethod
    def is_luma_url(cls, url: str) -> bool:
        """Check if a URL is a Luma event page."""
        return bool(cls.URL_PATTERN.match(url))

    @classmethod
    def extract_event_id(cls, url: str) -> str | None:
        """Extract the event ID from a Luma URL."""
        match = cls.URL_PATTERN.match(url)
        if match:
            return match.group("event_id")
        return None

    @classmethod
    def extract_from_markdown(cls, markdown: str, url: str) -> LumaEvent | None:
        """Extract event data from scraped markdown content.

        Luma pages typically include structured data that Firecrawl preserves.
        This method parses that content to extract event details.

        Args:
            markdown: Markdown content from Firecrawl scrape
            url: Original URL (used for ID extraction)

        Returns:
            LumaEvent if extraction successful, None otherwise
        """
        event_id = cls.extract_event_id(url)
        if not event_id:
            logger.warning("Could not extract event ID from URL: %s", url)
            return None

        try:
            # Try to find JSON-LD data in the markdown
            event_data = cls._extract_json_ld(markdown)
            if event_data:
                return cls._parse_json_ld(event_data, event_id, url)

            # Fall back to markdown parsing
            return cls._parse_markdown_content(markdown, event_id, url)

        except Exception as e:
            logger.error("Error extracting Luma event from %s: %s", url, e)
            return None

    @classmethod
    def _extract_json_ld(cls, markdown: str) -> dict[str, Any] | None:
        """Try to extract JSON-LD event data from markdown.

        Firecrawl may preserve script tags or metadata containing JSON-LD.
        """
        # Look for JSON-LD pattern in markdown
        json_ld_pattern = re.compile(
            r'\{"@context".*?"@type"\s*:\s*"Event".*?\}',
            re.DOTALL,
        )
        match = json_ld_pattern.search(markdown)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Look for Event schema pattern
        event_pattern = re.compile(
            r'```json\s*(\{[^`]*"@type"\s*:\s*"Event"[^`]*\})\s*```',
            re.DOTALL,
        )
        match = event_pattern.search(markdown)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    @classmethod
    def _parse_json_ld(
        cls, data: dict[str, Any], event_id: str, url: str
    ) -> LumaEvent:
        """Parse JSON-LD event data into LumaEvent."""
        # Parse dates
        start_time = None
        end_time = None
        if data.get("startDate"):
            try:
                start_time = datetime.fromisoformat(
                    data["startDate"].replace("Z", "+00:00")
                )
            except ValueError:
                pass
        if data.get("endDate"):
            try:
                end_time = datetime.fromisoformat(
                    data["endDate"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Parse location
        location = None
        is_online = False
        loc_data = data.get("location", {})
        if isinstance(loc_data, dict):
            if loc_data.get("@type") == "VirtualLocation":
                is_online = True
                location = loc_data.get("url") or "Online"
            else:
                address = loc_data.get("address", {})
                if isinstance(address, dict):
                    parts = [
                        address.get("streetAddress"),
                        address.get("addressLocality"),
                        address.get("addressRegion"),
                    ]
                    location = ", ".join(p for p in parts if p)
                elif isinstance(address, str):
                    location = address
                if not location:
                    location = loc_data.get("name")
        elif isinstance(loc_data, str):
            location = loc_data

        # Parse organizer
        host_name = None
        organizer = data.get("organizer", {})
        if isinstance(organizer, dict):
            host_name = organizer.get("name")
        elif isinstance(organizer, str):
            host_name = organizer

        # Parse offers for ticket price
        ticket_price = None
        offers = data.get("offers", {})
        if isinstance(offers, dict):
            price = offers.get("price")
            if price == 0 or price == "0":
                ticket_price = "Free"
            elif price:
                currency = offers.get("priceCurrency", "USD")
                ticket_price = f"${price}" if currency == "USD" else f"{price} {currency}"
        elif isinstance(offers, list) and offers:
            first_offer = offers[0]
            if isinstance(first_offer, dict):
                price = first_offer.get("price")
                if price == 0 or price == "0":
                    ticket_price = "Free"
                elif price:
                    currency = first_offer.get("priceCurrency", "USD")
                    ticket_price = f"${price}" if currency == "USD" else f"{price} {currency}"

        return LumaEvent(
            id=event_id,
            title=data.get("name", "Untitled Event"),
            description=data.get("description", ""),
            start_time=start_time,
            end_time=end_time,
            location=location,
            host_name=host_name,
            is_online=is_online,
            url=url,
            cover_image_url=data.get("image"),
            ticket_price=ticket_price,
        )

    @classmethod
    def _parse_markdown_content(
        cls, markdown: str, event_id: str, url: str
    ) -> LumaEvent:
        """Parse event data directly from markdown when JSON-LD is unavailable.

        This is a fallback that uses heuristics to extract data from
        the markdown structure.
        """
        lines = markdown.strip().split("\n")

        # First non-empty line is often the title
        title = "Untitled Event"
        for line in lines:
            line = line.strip()
            if line and not line.startswith(("http", "!", "[", "#")):
                # Remove markdown header markers
                title = re.sub(r"^#+\s*", "", line)
                break
            # Handle markdown headers
            if line.startswith("#"):
                title = re.sub(r"^#+\s*", "", line)
                break

        # Extract description (first paragraph after title)
        description = ""
        in_description = False
        for line in lines[1:]:
            line = line.strip()
            if not line:
                if in_description:
                    break
                continue
            if not line.startswith(("#", "!", "[", "http", "|", "-", "*")):
                in_description = True
                description += line + " "
        description = description.strip()[:500]

        # Try to find date patterns
        start_time = cls._extract_date_from_text(markdown)

        # Try to find location
        location = cls._extract_location_from_text(markdown)

        return LumaEvent(
            id=event_id,
            title=title,
            description=description,
            start_time=start_time,
            location=location,
            url=url,
        )

    @classmethod
    def _extract_date_from_text(cls, text: str) -> datetime | None:
        """Try to extract a date from text content."""
        # Common date patterns
        patterns = [
            # ISO format
            r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})",
            # "January 15, 2025 at 7:00 PM"
            r"([A-Z][a-z]+ \d{1,2},? \d{4}(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)",
            # "Jan 15 2025"
            r"([A-Z][a-z]{2} \d{1,2},? \d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                try:
                    # Try ISO format first
                    if "T" in date_str:
                        return datetime.fromisoformat(date_str)
                    # Try natural language parsing
                    # This is simplified - could use dateparser for better results
                except ValueError:
                    continue

        return None

    @classmethod
    def _extract_location_from_text(cls, text: str) -> str | None:
        """Try to extract a location from text content."""
        # Look for common location patterns
        patterns = [
            r"(?:Location|Venue|Where)[:\s]+([^\n]+)",
            r"(?:at|@)\s+([A-Z][^\n,]+(?:,\s*[A-Z][a-z]+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                if len(location) > 5:  # Avoid false positives
                    return location[:200]

        return None


# Singleton client instance
_firecrawl_client: FirecrawlClient | None = None


def get_firecrawl_client(api_key: str | None = None) -> FirecrawlClient | None:
    """Get the Firecrawl client singleton.

    Args:
        api_key: Optional API key. If not provided, returns None
                 (client must be initialized with a key).

    Returns:
        FirecrawlClient instance or None if no API key available.
    """
    global _firecrawl_client
    if _firecrawl_client is None:
        if api_key:
            _firecrawl_client = FirecrawlClient(api_key=api_key)
        else:
            return None
    return _firecrawl_client
