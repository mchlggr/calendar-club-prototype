"""
Eventbrite API client for event discovery.

Provides async methods to search and fetch events from Eventbrite.

NOTE: The official Eventbrite Event Search API (/v3/events/search/) was
deprecated in December 2019 and turned off in February 2020. This client
attempts to use alternative endpoints, but functionality is limited.

See: https://github.com/Automattic/eventbrite-api/issues/83

Current approach:
1. Try the internal destination API (used by eventbrite.com website)
2. Fall back gracefully if unavailable
"""

import logging
import os
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EventbriteEvent(BaseModel):
    """Parsed event from Eventbrite API."""

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


class EventbriteClient:
    """Async client for Eventbrite API.

    Uses the internal destination API since the official search API was deprecated.
    """

    # The official API base URL (for authenticated endpoints)
    API_BASE_URL = "https://www.eventbriteapi.com/v3"

    # The website's internal API (used for event discovery)
    WEB_BASE_URL = "https://www.eventbrite.com/api/v3"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EVENTBRITE_API_KEY")
        self._api_client: httpx.AsyncClient | None = None
        self._web_client: httpx.AsyncClient | None = None

    async def _get_api_client(self) -> httpx.AsyncClient:
        """Get client for official API (authenticated endpoints)."""
        if self._api_client is None:
            self._api_client = httpx.AsyncClient(
                base_url=self.API_BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
        return self._api_client

    async def _get_web_client(self) -> httpx.AsyncClient:
        """Get client for website internal API (discovery endpoints)."""
        if self._web_client is None:
            self._web_client = httpx.AsyncClient(
                base_url=self.WEB_BASE_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/json",
                    "Referer": "https://www.eventbrite.com/",
                },
                timeout=30.0,
            )
        return self._web_client

    async def close(self) -> None:
        """Close the HTTP clients."""
        if self._api_client:
            await self._api_client.aclose()
            self._api_client = None
        if self._web_client:
            await self._web_client.aclose()
            self._web_client = None

    async def search_events(
        self,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius: str = "25mi",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        categories: list[str] | None = None,
        free_only: bool = False,
        page_size: int = 10,
    ) -> list[EventbriteEvent]:
        """
        Search for events on Eventbrite using the destination API.

        NOTE: The official /v3/events/search/ endpoint was deprecated in 2020.
        This method uses Eventbrite's internal destination API which is used by
        their website but is not officially documented or supported.

        Args:
            location: Location string (e.g., "Columbus, OH")
            latitude: Latitude for geo search
            longitude: Longitude for geo search
            radius: Search radius (e.g., "10mi", "25km")
            start_date: Filter events starting after this date
            end_date: Filter events ending before this date
            categories: Category IDs to filter by
            free_only: Only return free events
            page_size: Number of results to return

        Returns:
            List of EventbriteEvent objects
        """
        # Try the destination API (internal website API)
        events = await self._search_via_destination_api(
            location=location,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            free_only=free_only,
            page_size=page_size,
        )

        if events:
            return events

        logger.info("Destination API returned no events, search unavailable")
        return []

    async def _search_via_destination_api(
        self,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        categories: list[str] | None = None,
        free_only: bool = False,
        page_size: int = 10,
    ) -> list[EventbriteEvent]:
        """
        Search using Eventbrite's internal destination API.

        This is the API used by eventbrite.com's website for event discovery.
        It's not officially documented but provides search functionality.
        """
        client = await self._get_web_client()

        # Build the destination search URL
        # Format: /destination/events/?q=<query>&place_id=<place>&dates=<dates>
        location_slug = quote(location or "Columbus--OH") if location else "Columbus--OH"

        params: dict[str, Any] = {
            "page_size": page_size,
            "expand": "event_sales_status,primary_venue,image,saves,ticket_availability",
        }

        # Date parameters
        if start_date:
            params["start_date.keyword"] = "this_week"
            # Or use specific date range
            params["start_date.range_start"] = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        if end_date:
            params["start_date.range_end"] = end_date.strftime("%Y-%m-%dT%H:%M:%S")

        # Category filter - destination API uses different category format
        if categories:
            category_map = {
                "ai": "science-and-tech",
                "tech": "science-and-tech",
                "startup": "business",
                "business": "business",
                "community": "community",
                "networking": "business",
            }
            cat_slugs = [category_map.get(c, c) for c in categories if c in category_map]
            if cat_slugs:
                params["subcategories"] = ",".join(cat_slugs)

        # Price filter
        if free_only:
            params["price"] = "free"

        try:
            # Try the destination events endpoint
            endpoint = f"/destination/events/{location_slug}/"
            logger.debug(
                "🌐 [Eventbrite] Starting search | endpoint=%s location=%s",
                endpoint,
                location or "Columbus--OH",
            )
            start_time = time.perf_counter()

            response = await client.get(endpoint, params=params)

            if response.status_code == 404:
                # Try alternative endpoint format
                logger.debug("⚠️ [Eventbrite] 404 on destination API, trying search endpoint")
                response = await client.get(
                    "/destination/search/",
                    params={**params, "q": location or "tech events"},
                )

            if response.status_code == 404:
                elapsed = time.perf_counter() - start_time
                logger.debug(
                    "❌ [Eventbrite] API unavailable (404) | duration=%.2fs",
                    elapsed,
                )
                logger.warning(
                    "Eventbrite destination API not available (404). "
                    "The internal API may have changed."
                )
                return []

            response.raise_for_status()
            data = response.json()

            events = []
            # Destination API returns events in "events" array
            for event_data in data.get("events", []):
                event = self._parse_destination_event(event_data)
                if event:
                    events.append(event)

            elapsed = time.perf_counter() - start_time
            if events:
                logger.debug(
                    "✅ [Eventbrite] Complete | events=%d duration=%.2fs",
                    len(events),
                    elapsed,
                )
            else:
                logger.debug(
                    "📭 [Eventbrite] No events found | duration=%.2fs",
                    elapsed,
                )
            return events

        except httpx.HTTPError as e:
            elapsed = time.perf_counter() - start_time if 'start_time' in locals() else 0
            logger.debug(
                "❌ [Eventbrite] HTTP error | error=%s duration=%.2fs",
                str(e)[:100],
                elapsed,
            )
            logger.warning("Eventbrite destination API error: %s", e)
            return []

    def _parse_destination_event(self, data: dict[str, Any]) -> EventbriteEvent | None:
        """Parse event data from the destination API format."""
        try:
            # Destination API has slightly different structure
            event_data = data.get("event", data)  # May be nested or direct

            # Parse dates
            start_data = event_data.get("start", {})
            start_str = start_data.get("utc") or start_data.get("local", "")
            if not start_str:
                return None
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

            end_data = event_data.get("end", {})
            end_time = None
            end_str = end_data.get("utc") or end_data.get("local")
            if end_str:
                end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

            # Parse venue - destination API may use primary_venue
            venue = event_data.get("primary_venue") or event_data.get("venue", {})
            venue_name = venue.get("name")
            venue_address = None
            if venue.get("address"):
                addr = venue["address"]
                parts = [
                    addr.get("address_1"),
                    addr.get("city"),
                    addr.get("region"),
                ]
                venue_address = ", ".join(p for p in parts if p)

            # Parse pricing
            is_free = event_data.get("is_free", True)
            price_amount = None
            ticket_info = event_data.get("ticket_availability", {})
            if not is_free and ticket_info.get("minimum_ticket_price"):
                price_data = ticket_info["minimum_ticket_price"]
                price_amount = int(price_data.get("major_value", 0))

            # Get logo/image
            logo_url = None
            if event_data.get("image"):
                logo_url = event_data["image"].get("url")
            elif event_data.get("logo"):
                logo_url = event_data["logo"].get("url")

            # Get title - destination API may use different field
            title = (
                event_data.get("name", {}).get("text")
                or event_data.get("name", {}).get("html")
                or event_data.get("title")
                or "Untitled Event"
            )

            # Get description
            description = (
                event_data.get("description", {}).get("text")
                or event_data.get("summary")
                or ""
            )[:500]

            return EventbriteEvent(
                id=event_data.get("id", ""),
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                venue_name=venue_name,
                venue_address=venue_address,
                category="community",  # Default category
                is_free=is_free,
                price_amount=price_amount,
                url=event_data.get("url"),
                logo_url=logo_url,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Error parsing destination event: %s", e)
            return None

    def _parse_event(self, data: dict[str, Any]) -> EventbriteEvent | None:
        """Parse raw Eventbrite API response into EventbriteEvent."""
        try:
            # Parse dates
            start_data = data.get("start", {})
            start_time = datetime.fromisoformat(
                start_data.get("utc", "").replace("Z", "+00:00")
            )

            end_data = data.get("end", {})
            end_time = None
            if end_data.get("utc"):
                end_time = datetime.fromisoformat(
                    end_data["utc"].replace("Z", "+00:00")
                )

            # Parse venue
            venue = data.get("venue", {})
            venue_name = venue.get("name")
            venue_address = None
            if venue.get("address"):
                addr = venue["address"]
                parts = [
                    addr.get("address_1"),
                    addr.get("city"),
                    addr.get("region"),
                ]
                venue_address = ", ".join(p for p in parts if p)

            # Parse pricing
            is_free = data.get("is_free", True)
            price_amount = None
            ticket_info = data.get("ticket_availability", {})
            if not is_free and ticket_info.get("minimum_ticket_price"):
                price_data = ticket_info["minimum_ticket_price"]
                # Price is in cents
                price_amount = int(price_data.get("major_value", 0))

            # Get logo
            logo_url = None
            if data.get("logo"):
                logo_url = data["logo"].get("url")

            # Map category
            category = "community"
            cat_id = data.get("category_id")
            if cat_id == "102":
                category = "ai"
            elif cat_id == "101":
                category = "startup"

            return EventbriteEvent(
                id=data["id"],
                title=data.get("name", {}).get("text", "Untitled Event"),
                description=data.get("description", {}).get("text", "")[:500],
                start_time=start_time,
                end_time=end_time,
                venue_name=venue_name,
                venue_address=venue_address,
                category=category,
                is_free=is_free,
                price_amount=price_amount,
                url=data.get("url"),
                logo_url=logo_url,
            )

        except (KeyError, ValueError) as e:
            logger.warning("Error parsing event: %s", e)
            return None


# Singleton instance
_client: EventbriteClient | None = None


def get_eventbrite_client() -> EventbriteClient:
    """Get the singleton Eventbrite client."""
    global _client
    if _client is None:
        _client = EventbriteClient()
    return _client


async def search_events_adapter(profile: Any) -> list[EventbriteEvent]:
    """
    Adapter for registry pattern - searches Eventbrite using a SearchProfile.

    Args:
        profile: SearchProfile with search criteria

    Returns:
        List of EventbriteEvent objects
    """
    client = get_eventbrite_client()

    # Extract search parameters from profile
    location = "Columbus, OH"  # Default location
    categories = profile.categories if hasattr(profile, "categories") else None
    free_only = profile.free_only if hasattr(profile, "free_only") else False

    # Parse time window
    start_date: datetime | None = None
    end_date: datetime | None = None
    if hasattr(profile, "time_window") and profile.time_window:
        if profile.time_window.start:
            start_value = profile.time_window.start
            if isinstance(start_value, str):
                start_date = datetime.fromisoformat(start_value)
            else:
                start_date = start_value
        if profile.time_window.end:
            end_value = profile.time_window.end
            if isinstance(end_value, str):
                end_date = datetime.fromisoformat(end_value)
            else:
                end_date = end_value

    # Log the complete outbound query for debugging
    logger.debug(
        "📤 [Eventbrite] Outbound Query | location='%s' start=%s end=%s categories=%s free_only=%s",
        location,
        start_date,
        end_date,
        categories,
        free_only,
    )

    return await client.search_events(
        location=location,
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        free_only=free_only,
        page_size=10,
    )


def register_eventbrite_source() -> None:
    """Register Eventbrite as an event source in the global registry."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("EVENTBRITE_API_KEY", "")

    source = EventSource(
        name="eventbrite",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=10,  # High priority - structured event data
        description="Eventbrite event platform with structured event data",
    )
    register_event_source(source)
