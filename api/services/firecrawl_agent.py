"""
Firecrawl Agent for autonomous event discovery.

Uses the /agent endpoint for autonomous web research that discovers
events without requiring URLs - just a natural language prompt.
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from firecrawl import AsyncFirecrawl
from pydantic import BaseModel, Field

from api.services.firecrawl import ScrapedEvent

logger = logging.getLogger(__name__)


class AgentEventItem(BaseModel):
    """Single event extracted by Firecrawl Agent."""

    title: str = Field(description="Event title or name")
    start_date: str = Field(
        description="Date in 'Month Day, Year' format (e.g., 'January 15, 2026'). MUST include year."
    )
    start_time: str | None = Field(
        default=None,
        description="Time with AM/PM (e.g., '7:00 PM')"
    )
    venue_name: str | None = Field(
        default=None,
        description="Venue name or 'Online' for virtual events"
    )
    venue_address: str | None = Field(
        default=None,
        description="Full address with city, state"
    )
    price: str = Field(
        default="Free",
        description="'Free' or price like '$25'"
    )
    url: str = Field(description="Event page URL")
    description: str | None = Field(
        default=None,
        description="Brief event description"
    )


class AgentEventsOutput(BaseModel):
    """Structured output from Firecrawl Agent for events."""

    events: list[AgentEventItem] = Field(
        description="List of events discovered"
    )


def _parse_price(price_str: str | None) -> tuple[bool, int | None]:
    """Parse price string into (is_free, price_cents)."""
    if not price_str:
        return True, None

    price_lower = price_str.lower().strip()
    if price_lower in ("free", "no cover", "complimentary", "donation", "rsvp", ""):
        return True, None

    match = re.search(r"\$?(\d+(?:\.\d{2})?)", price_str)
    if match:
        price = float(match.group(1))
        return False, int(price * 100)

    return True, None


def _parse_datetime(
    date_str: str | None,
    time_str: str | None,
) -> datetime | None:
    """Parse date and time strings into datetime."""
    if not date_str:
        return None

    try:
        from dateutil import parser as dateutil_parser

        combined = date_str
        if time_str:
            combined = f"{date_str} {time_str}"

        return dateutil_parser.parse(combined, fuzzy=True)
    except Exception:
        return None


class FirecrawlAgentClient:
    """
    Client for Firecrawl Agent API.

    Uses the /agent endpoint for autonomous web research
    that discovers events without requiring URLs.
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

    async def discover_events(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        timeout: int = 120,
        max_credits: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Discover events using the Firecrawl agent.

        Args:
            prompt: Natural language description of events to find
            schema: Optional Pydantic model for structured output
            timeout: Maximum time to wait (seconds)
            max_credits: Optional credit limit

        Returns:
            List of event dictionaries
        """
        if not self.api_key:
            logger.warning("FIRECRAWL_API_KEY not set")
            return []

        client = self._get_client()

        try:
            logger.debug(
                "🤖 [Firecrawl Agent] Starting | prompt=%s...",
                prompt[:50]
            )

            result = await client.agent(
                prompt=prompt,
                schema=schema,
                poll_interval=5,  # Poll every 5 seconds
                timeout=timeout,
                max_credits=max_credits,
            )

            # Extract events from result
            events = []
            if hasattr(result, 'data') and result.data:
                data = result.data
                if isinstance(data, dict) and 'events' in data:
                    events = data['events']
                elif isinstance(data, list):
                    events = data

            logger.info(
                "✅ [Firecrawl Agent] Complete | events=%d",
                len(events)
            )
            return events

        except asyncio.TimeoutError:
            logger.warning(
                "⏰ [Firecrawl Agent] Timeout after %ds",
                timeout
            )
            return []
        except Exception as e:
            logger.warning("Firecrawl agent error: %s", e)
            return []


# Singleton instance
_agent_client: FirecrawlAgentClient | None = None


def get_firecrawl_agent_client() -> FirecrawlAgentClient:
    """Get the singleton Firecrawl Agent client."""
    global _agent_client
    if _agent_client is None:
        _agent_client = FirecrawlAgentClient()
    return _agent_client


async def firecrawl_agent_adapter(profile: Any) -> list[ScrapedEvent]:
    """
    Adapter for registry pattern - uses Firecrawl Agent for discovery.

    The agent autonomously searches the web based on the prompt,
    handling site navigation and extraction automatically.
    """
    client = get_firecrawl_agent_client()

    # Build natural language prompt from profile
    prompt_parts = [
        "Find upcoming events",
    ]

    # Add location
    location = "Columbus, Ohio"  # Default
    if hasattr(profile, "location") and profile.location:
        location = profile.location
    prompt_parts.append(f"in {location}")

    # Add time window
    if hasattr(profile, "time_window") and profile.time_window:
        if profile.time_window.start:
            start_str = profile.time_window.start.strftime("%B %d, %Y")
            prompt_parts.append(f"starting from {start_str}")
        if profile.time_window.end:
            end_str = profile.time_window.end.strftime("%B %d, %Y")
            prompt_parts.append(f"until {end_str}")
    else:
        # Default to next 2 weeks
        prompt_parts.append("in the next 2 weeks")

    # Add categories
    if hasattr(profile, "categories") and profile.categories:
        categories = ", ".join(profile.categories)
        prompt_parts.append(f"related to: {categories}")

    # Add keywords
    if hasattr(profile, "keywords") and profile.keywords:
        keywords = ", ".join(profile.keywords)
        prompt_parts.append(f"about: {keywords}")

    # Add free filter
    if hasattr(profile, "free_only") and profile.free_only:
        prompt_parts.append("that are free to attend")

    # Add extraction instructions
    prompt_parts.append(
        "For each event, extract: title, date (with full year), "
        "time, venue name, venue address, price, event URL, "
        "and a brief description."
    )

    prompt = ". ".join(prompt_parts)

    logger.debug(
        "📤 [Firecrawl Agent] Outbound Query | prompt=%s",
        prompt[:100]
    )

    start_time = time.perf_counter()
    raw_events = await client.discover_events(
        prompt=prompt,
        schema=AgentEventsOutput,
        timeout=120,  # 2 minute timeout
        max_credits=50,  # Limit cost per query
    )
    elapsed = time.perf_counter() - start_time

    logger.debug(
        "📥 [Firecrawl Agent] Fetched | events=%d duration=%.2fs",
        len(raw_events),
        elapsed,
    )

    # Convert to ScrapedEvent format
    events = []
    for raw in raw_events:
        try:
            start_dt = _parse_datetime(
                raw.get("start_date"),
                raw.get("start_time"),
            )
            is_free, price_amount = _parse_price(raw.get("price"))

            event = ScrapedEvent(
                source="firecrawl-agent",
                event_id=raw.get("url", "") or str(hash(raw.get("title", ""))),
                title=raw.get("title", "Untitled"),
                description=raw.get("description") or "",
                start_time=start_dt,
                end_time=None,
                venue_name=raw.get("venue_name"),
                venue_address=raw.get("venue_address"),
                category="community",  # Default category
                is_free=is_free,
                price_amount=price_amount,
                url=raw.get("url", ""),
                logo_url=None,
                raw_data=raw,
            )
            events.append(event)
        except Exception as e:
            logger.warning(
                "Failed to parse agent event: %s | error=%s",
                raw.get("title"),
                e,
            )
            continue

    # Post-filter by time window (agent may return slightly outside range)
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


def register_firecrawl_agent_source() -> None:
    """Register Firecrawl Agent as an event source."""
    from api.services.base import EventSource, register_event_source

    api_key = os.getenv("FIRECRAWL_API_KEY", "")

    source = EventSource(
        name="firecrawl-agent",
        search_fn=firecrawl_agent_adapter,
        is_enabled_fn=lambda: bool(api_key),
        priority=35,  # After other sources - agent is slower but broader
        description="Firecrawl Agent for autonomous event discovery",
    )
    register_event_source(source)
