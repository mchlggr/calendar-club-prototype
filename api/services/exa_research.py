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
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from api.services.exa_client import ExaSearchResult

logger = logging.getLogger(__name__)


class ExaResearchResult(BaseModel):
    """Result from Exa Research task."""

    task_id: str
    status: str  # "pending", "running", "completed", "failed"
    results: list[ExaSearchResult] | None = None
    summary: str | None = None


# Schema for structured event extraction via Exa Research
EVENT_RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "description": "List of events found",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title",
                    },
                    "start_date": {
                        "type": "string",
                        "description": (
                            "Date in 'Month Day, Year' format "
                            "(e.g., 'January 15, 2026'). MUST include year."
                        ),
                    },
                    "start_time": {
                        "type": ["string", "null"],
                        "description": "Time with AM/PM (e.g., '7:00 PM')",
                    },
                    "venue_name": {
                        "type": ["string", "null"],
                        "description": "Venue name or 'Online' for virtual events",
                    },
                    "venue_address": {
                        "type": ["string", "null"],
                        "description": "Full address with city, state",
                    },
                    "price": {
                        "type": "string",
                        "description": "'Free' or price like '$25'",
                    },
                    "url": {
                        "type": "string",
                        "description": "Event page URL",
                    },
                    "description": {
                        "type": ["string", "null"],
                        "description": "Brief event description",
                    },
                },
                "required": ["title", "start_date", "url"],
            },
        }
    },
    "required": ["events"],
}


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
        output_schema: dict[str, Any] | None = None,
    ) -> Any:
        """Synchronous research task creation."""
        client = self._get_client()

        kwargs: dict[str, Any] = {"instructions": query}
        if output_schema:
            kwargs["output_schema"] = output_schema

        return client.research.create(**kwargs)

    async def create_research_task(
        self,
        query: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Create a research task for deep event discovery.

        Args:
            query: Research question/topic
            output_schema: Optional schema for structured output

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

            task_id = getattr(result, 'id', None) or result.get('id') if isinstance(result, dict) else None
            if task_id:
                logger.debug("✅ [Exa Research] Task created | id=%s", task_id)
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
            results = None

            if hasattr(result, 'results') and result.results:
                results = [
                    ExaSearchResult(
                        id=getattr(r, 'id', ''),
                        title=getattr(r, 'title', 'Untitled'),
                        url=getattr(r, 'url', ''),
                        text=getattr(r, 'text', None),
                    )
                    for r in result.results
                ]

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

    # Create research task WITH schema for structured output
    task_id = await client.create_research_task(
        query,
        output_schema=EVENT_RESEARCH_SCHEMA,
    )
    if not task_id:
        return []

    # Poll for results (max 60 seconds)
    max_polls = 12
    poll_interval = 5.0

    for _ in range(max_polls):
        await asyncio.sleep(poll_interval)

        status = await client.get_task_status(task_id)
        if not status:
            continue

        if status.status == "completed":
            return status.results or []
        elif status.status == "failed":
            logger.warning("Exa research task %s failed", task_id)
            return []

    logger.warning("Exa research task %s timed out", task_id)
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
