"""
Exa Research API client for deep event discovery.

Uses the SDK's research.create_task() for multi-step web research
that discovers events through comprehensive analysis.
"""

import asyncio
import logging
import os
from typing import Any

from exa_py import Exa
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.services.exa_client import ExaSearchResult

logger = logging.getLogger(__name__)


class ExaResearchResult(BaseModel):
    """Result from Exa Research task."""

    task_id: str
    status: str  # "pending", "running", "completed", "failed"
    results: list[ExaSearchResult] | None = None
    summary: str | None = None


class ResearchEventItem(BaseModel):
    """Single event extracted by Exa Research."""

    title: str = Field(description="Event title")
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


class ResearchEventsOutput(BaseModel):
    """Structured output from Exa Research for events."""

    events: list[ResearchEventItem] = Field(
        description="List of events found"
    )


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
        output_schema: type[BaseModel] | None = None,
    ) -> Any:
        """Synchronous research task creation."""
        client = self._get_client()

        kwargs: dict[str, Any] = {"instructions": query}
        if output_schema:
            # Pass the Pydantic model class directly - Exa SDK handles conversion
            kwargs["output_schema"] = output_schema

        return client.research.create(**kwargs)

    async def create_research_task(
        self,
        query: str,
        output_schema: type[BaseModel] | None = None,
    ) -> str | None:
        """
        Create a research task for deep event discovery.

        Args:
            query: Research question/topic
            output_schema: Optional Pydantic model class for structured output

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

            # Extract task ID - SDK returns ResearchRunningDto with research_id
            task_id = None
            if hasattr(result, 'research_id'):
                task_id = result.research_id
            elif hasattr(result, 'id'):
                task_id = result.id
            elif isinstance(result, dict):
                task_id = result.get('research_id') or result.get('id')

            if task_id:
                logger.debug("✅ [Exa Research] Task created | id=%s", task_id)
            else:
                logger.warning("🔬 [Exa Research] No task ID in response | type=%s result=%s", type(result).__name__, result)
            return task_id

        except Exception as e:
            logger.warning("Exa research task creation error: %s", e)
            return None

    def _sync_get_task_status(self, task_id: str) -> Any:
        """Synchronous task status check."""
        client = self._get_client()
        return client.research.get(task_id)

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
            logger.debug("⏳ [Exa Research] Poll status | id=%s status=%s type=%s", task_id, status, type(result).__name__)

            results = None

            # SDK returns nested structure: result.output.parsed['events']
            # ResearchOutput has: content (JSON string), parsed (dict with events)
            output_obj = getattr(result, 'output', None)
            raw_events = None

            if output_obj is not None:
                # First try: output_obj.parsed['events'] (the actual structure)
                parsed = getattr(output_obj, 'parsed', None)
                if parsed and isinstance(parsed, dict):
                    raw_events = parsed.get('events')
                    logger.debug("📦 [Exa Research] Parsed output | events=%d", len(raw_events) if raw_events else 0)

                # Fallback: direct events attribute
                if not raw_events and hasattr(output_obj, 'events'):
                    raw_events = output_obj.events

            # Fallback: check direct attributes on result
            if not raw_events:
                raw_events = getattr(result, 'events', None) or getattr(result, 'results', None)

            if raw_events and isinstance(raw_events, list):
                logger.debug("📊 [Exa Research] Got events | count=%d", len(raw_events))
                results = []
                for r in raw_events:
                    # Handle both dict and object responses
                    if isinstance(r, dict):
                        event = ExaSearchResult(
                            id=r.get('url', '') or r.get('id', ''),
                            title=r.get('title', 'Untitled'),
                            url=r.get('url', ''),
                            text=r.get('description'),
                            # Store extra fields in extracted_event for downstream use
                            extracted_event={
                                'start_date': r.get('start_date'),
                                'start_time': r.get('start_time'),
                                'venue_name': r.get('venue_name'),
                                'venue_address': r.get('venue_address'),
                                'price': r.get('price'),
                            }
                        )
                    else:
                        event = ExaSearchResult(
                            id=getattr(r, 'url', '') or getattr(r, 'id', ''),
                            title=getattr(r, 'title', 'Untitled'),
                            url=getattr(r, 'url', ''),
                            text=getattr(r, 'description', None) or getattr(r, 'text', None),
                        )
                    results.append(event)

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
    client = get_exa_research_client()

    # Build research query with explicit extraction instructions
    query_parts = [
        "Find upcoming events in Columbus, Ohio",
        (
            "For each event, extract: title, date (with full year), "
            "time, venue, address, price, URL, and description"
        ),
    ]

    if hasattr(profile, "time_window") and profile.time_window:
        if profile.time_window.start:
            query_parts.append(
                f"Events starting from {profile.time_window.start.strftime('%B %d, %Y')}"
            )
        if profile.time_window.end:
            query_parts.append(
                f"Events before {profile.time_window.end.strftime('%B %d, %Y')}"
            )

    if hasattr(profile, "categories") and profile.categories:
        query_parts.append(f"Focus on: {', '.join(profile.categories)}")

    if hasattr(profile, "keywords") and profile.keywords:
        query_parts.append(f"Related to: {', '.join(profile.keywords)}")

    query = ". ".join(query_parts)

    # Create research task WITH Pydantic model for structured output
    task_id = await client.create_research_task(
        query,
        output_schema=ResearchEventsOutput,
    )
    if not task_id:
        logger.warning("Exa research task failed to create")
        return []

    # Poll for results (max 120 seconds for deep research)
    max_polls = 24
    poll_interval = 5.0

    for poll_num in range(max_polls):
        await asyncio.sleep(poll_interval)

        status = await client.get_task_status(task_id)
        if not status:
            logger.debug("⏳ [Exa Research] Poll %d/%d | id=%s status=None", poll_num + 1, max_polls, task_id)
            continue

        logger.debug(
            "⏳ [Exa Research] Poll %d/%d | id=%s status=%s results=%s",
            poll_num + 1, max_polls, task_id, status.status,
            len(status.results) if status.results else 0
        )

        # Check for completion - handle various status strings
        if status.status in ("completed", "complete", "success", "done"):
            if status.results:
                logger.info("✅ [Exa Research] Task complete | id=%s events=%d", task_id, len(status.results))
                return status.results
            else:
                logger.warning("⚠️ [Exa Research] Task complete but no results | id=%s", task_id)
                return []
        elif status.status in ("failed", "error"):
            logger.warning("❌ [Exa Research] Task failed | id=%s", task_id)
            return []

    logger.warning("⏰ [Exa Research] Task timed out after %ds | id=%s", int(max_polls * poll_interval), task_id)
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
