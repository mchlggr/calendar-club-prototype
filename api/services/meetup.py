"""
Meetup GraphQL API client for event discovery.

Provides async methods to search and fetch events from Meetup using their
GraphQL API.

API Documentation: https://www.meetup.com/graphql/guide/
"""

import logging
import time
from datetime import datetime
from typing import Any

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from pydantic import BaseModel

from api.config import get_settings
from api.models import SearchProfile
from api.services.base import EventSource, get_event_source_registry

logger = logging.getLogger(__name__)


class MeetupEvent(BaseModel):
    """Parsed event from Meetup GraphQL API."""

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
    image_url: str | None = None
    group_name: str | None = None


# GraphQL query for searching events
SEARCH_EVENTS_QUERY = gql("""
    query SearchEvents(
        $query: String!
        $lat: Float!
        $lon: Float!
        $radius: Int
        $startDateRange: ZonedDateTime
        $endDateRange: ZonedDateTime
        $first: Int
    ) {
        rankedEvents(
            filter: {
                query: $query
                lat: $lat
                lon: $lon
                radius: $radius
                startDateRange: $startDateRange
                endDateRange: $endDateRange
            }
            first: $first
        ) {
            count
            edges {
                node {
                    id
                    title
                    description
                    dateTime
                    endTime
                    eventUrl
                    going
                    isOnline
                    images {
                        baseUrl
                    }
                    venue {
                        name
                        address
                        city
                        state
                        country
                    }
                    group {
                        name
                        urlname
                    }
                    feeSettings {
                        amount
                        currency
                        required
                    }
                    eventType
                }
            }
        }
    }
""")


class MeetupClient:
    """Async client for Meetup GraphQL API."""

    API_URL = "https://api.meetup.com/gql"

    def __init__(self, access_token: str | None = None):
        settings = get_settings()
        self.access_token = access_token or settings.meetup_access_token
        self._client: Client | None = None

    def _get_transport(self) -> AIOHTTPTransport:
        """Create authenticated transport for GraphQL client."""
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        return AIOHTTPTransport(
            url=self.API_URL,
            headers=headers,
            timeout=30,
        )

    async def _get_client(self) -> Client:
        """Get or create the GraphQL client."""
        if self._client is None:
            transport = self._get_transport()
            self._client = Client(
                transport=transport,
                fetch_schema_from_transport=False,
            )
        return self._client

    async def close(self) -> None:
        """Close the GraphQL client."""
        if self._client is not None:
            await self._client.close_async()
            self._client = None

    async def search_events(
        self,
        query: str = "tech",
        latitude: float = 39.9612,  # Columbus, OH default
        longitude: float = -82.9988,
        radius: int = 50,  # miles
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 10,
    ) -> list[MeetupEvent]:
        """
        Search for events on Meetup.

        Args:
            query: Search query string (e.g., "tech", "AI", "python")
            latitude: Search center latitude
            longitude: Search center longitude
            radius: Search radius in miles
            start_date: Filter events starting after this date
            end_date: Filter events ending before this date
            limit: Maximum number of results

        Returns:
            List of MeetupEvent objects
        """
        if not self.access_token:
            logger.warning("Meetup API: No access token configured")
            return []

        try:
            client = await self._get_client()

            # Build variables
            variables: dict[str, Any] = {
                "query": query,
                "lat": latitude,
                "lon": longitude,
                "radius": radius,
                "first": limit,
            }

            # Add date filters if provided
            if start_date:
                variables["startDateRange"] = start_date.isoformat()
            if end_date:
                variables["endDateRange"] = end_date.isoformat()

            logger.info("Meetup search: query=%s, lat=%s, lon=%s", query, latitude, longitude)

            # Execute query
            async with client as session:
                result = await session.execute(SEARCH_EVENTS_QUERY, variable_values=variables)

            # Parse results
            events = []
            ranked_events = result.get("rankedEvents", {})
            edges = ranked_events.get("edges", [])

            logger.info("Meetup returned %d results", len(edges))

            for edge in edges:
                node = edge.get("node", {})
                event = self._parse_event(node)
                if event:
                    events.append(event)

            return events

        except Exception as e:
            logger.error("Meetup API error: %s", e, exc_info=True)
            return []

    def _parse_event(self, data: dict[str, Any]) -> MeetupEvent | None:
        """Parse GraphQL event data into MeetupEvent."""
        try:
            # Parse datetime
            date_str = data.get("dateTime")
            if not date_str:
                return None
            start_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

            # Parse end time
            end_time = None
            end_str = data.get("endTime")
            if end_str:
                end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

            # Parse venue
            venue = data.get("venue") or {}
            venue_name = venue.get("name")
            venue_address = None
            if venue:
                parts = [
                    venue.get("address"),
                    venue.get("city"),
                    venue.get("state"),
                ]
                venue_address = ", ".join(p for p in parts if p)

            # Parse fee/pricing
            is_free = True
            price_amount = None
            fee_settings = data.get("feeSettings")
            if fee_settings and fee_settings.get("required"):
                is_free = False
                price_amount = int(fee_settings.get("amount", 0))

            # Get image
            image_url = None
            images = data.get("images", [])
            if images and len(images) > 0:
                image_url = images[0].get("baseUrl")

            # Get group info
            group = data.get("group") or {}
            group_name = group.get("name")

            # Map event type to category
            event_type = data.get("eventType", "").lower()
            category = "community"
            if "tech" in event_type or "coding" in event_type:
                category = "tech"

            return MeetupEvent(
                id=data.get("id", ""),
                title=data.get("title", "Untitled Event"),
                description=(data.get("description") or "")[:500],
                start_time=start_time,
                end_time=end_time,
                venue_name=venue_name,
                venue_address=venue_address,
                category=category,
                is_free=is_free,
                price_amount=price_amount,
                url=data.get("eventUrl"),
                image_url=image_url,
                group_name=group_name,
            )

        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Error parsing Meetup event: %s", e)
            return None


# Singleton instance
_client: MeetupClient | None = None


def get_meetup_client() -> MeetupClient:
    """Get the singleton Meetup client."""
    global _client
    if _client is None:
        _client = MeetupClient()
    return _client


async def search_events_adapter(profile: SearchProfile) -> list[MeetupEvent]:
    """
    Adapter function for EventSourceRegistry.

    Converts SearchProfile to Meetup search parameters and returns events.
    """
    start = time.perf_counter()
    client = get_meetup_client()

    # Build query from categories and keywords
    query_parts = []
    if hasattr(profile, "categories") and profile.categories:
        query_parts.extend(profile.categories)
    if hasattr(profile, "keywords") and profile.keywords:
        query_parts.extend(profile.keywords)

    query = " ".join(query_parts) if query_parts else "events"

    # Extract time window
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
    latitude = 39.9612  # Columbus, OH
    longitude = -82.9988
    radius = 50

    logger.debug(
        "📤 [Meetup] Outbound Query | query='%s' lat=%s lon=%s radius=%d start=%s end=%s",
        query,
        latitude,
        longitude,
        radius,
        start_date,
        end_date,
    )

    events = await client.search_events(
        query=query,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        start_date=start_date,
        end_date=end_date,
        limit=15,
    )

    elapsed = time.perf_counter() - start
    if events:
        logger.debug(
            "✅ [Meetup] Complete | events=%d duration=%.2fs",
            len(events),
            elapsed,
        )
    else:
        logger.debug(
            "📭 [Meetup] No events found | duration=%.2fs",
            elapsed,
        )

    return events


def register_meetup_source() -> None:
    """Register Meetup as an event source."""
    settings = get_settings()

    source = EventSource(
        name="meetup",
        search_fn=search_events_adapter,
        is_enabled_fn=lambda: bool(settings.meetup_access_token),
        priority=15,  # Between Eventbrite (10) and Exa (20)
        description="Meetup GraphQL API for community events",
    )

    registry = get_event_source_registry()
    registry.register(source)
