"""
Eventbrite API client for event discovery.

Provides async methods to search and fetch events from Eventbrite.
"""

import os
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel


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
    """Async client for Eventbrite API."""

    BASE_URL = "https://www.eventbriteapi.com/v3"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("EVENTBRITE_API_KEY")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

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
        Search for events on Eventbrite.

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
        if not self.api_key:
            return []

        client = await self._get_client()

        params: dict[str, Any] = {
            "expand": "venue,ticket_availability",
            "page_size": page_size,
        }

        # Location parameters
        if latitude and longitude:
            params["location.latitude"] = str(latitude)
            params["location.longitude"] = str(longitude)
            params["location.within"] = radius
        elif location:
            params["location.address"] = location
            params["location.within"] = radius

        # Date range
        if start_date:
            params["start_date.range_start"] = start_date.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if end_date:
            params["start_date.range_end"] = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Categories (Eventbrite uses numeric category IDs)
        if categories:
            category_map = {
                "ai": "102",  # Science & Technology
                "tech": "102",
                "startup": "101",  # Business & Professional
                "business": "101",
                "community": "113",  # Community & Culture
                "networking": "101",
            }
            cat_ids = [category_map.get(c, c) for c in categories if c in category_map]
            if cat_ids:
                params["categories"] = ",".join(cat_ids)

        # Price filter
        if free_only:
            params["price"] = "free"

        try:
            response = await client.get("/events/search/", params=params)
            response.raise_for_status()
            data = response.json()

            events = []
            for event_data in data.get("events", []):
                event = self._parse_event(event_data)
                if event:
                    events.append(event)

            return events

        except httpx.HTTPError as e:
            # Log error but don't crash - return empty list
            print(f"Eventbrite API error: {e}")
            return []

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
            print(f"Error parsing event: {e}")
            return None


# Singleton instance
_client: EventbriteClient | None = None


def get_eventbrite_client() -> EventbriteClient:
    """Get the singleton Eventbrite client."""
    global _client
    if _client is None:
        _client = EventbriteClient()
    return _client
