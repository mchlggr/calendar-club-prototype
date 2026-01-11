"""
SearchAgent for Phase 2: Search and refinement.

Shows search results based on SearchProfile and refines
based on user feedback (Yes/No/Maybe ratings).
"""

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from agents import Agent, function_tool

from api.config import get_settings
from api.models import EventFeedback, SearchProfile
from api.services import (
    EventbriteEvent,
    ExaSearchResult,
    get_event_source_registry,
)

logger = logging.getLogger(__name__)


# Tool input/output models for strict schema compatibility
class EventResult(BaseModel):
    """An event from search results."""

    id: str
    title: str
    date: str = Field(description="ISO 8601 datetime string")
    location: str
    category: str
    description: str
    is_free: bool
    price_amount: int | None = None
    distance_miles: float
    url: str | None = None


class RefinementInput(BaseModel):
    """Input for refine_results tool."""

    feedback: list[EventFeedback] = Field(description="User feedback on events")


class RefinementOutput(BaseModel):
    """Output from refine_results tool."""

    events: list[EventResult]
    explanation: str
    source: str = Field(
        default="refined", description="Data source: 'refined' or 'unavailable'"
    )


class SearchResult(BaseModel):
    """Result from search_events tool."""

    events: list[EventResult]
    source: str = Field(description="Data source: 'eventbrite' or 'unavailable'")
    message: str | None = Field(
        default=None, description="User-facing message about data source"
    )


def _convert_eventbrite_event(event: EventbriteEvent) -> EventResult:
    """Convert EventbriteEvent to EventResult format."""
    venue = event.venue_name or "TBD"
    if event.venue_address:
        venue = f"{venue}, {event.venue_address}"

    return EventResult(
        id=event.id,
        title=event.title,
        date=event.start_time.isoformat(),
        location=venue,
        category=event.category,
        description=event.description[:200] if event.description else "",
        is_free=event.is_free,
        price_amount=event.price_amount,
        distance_miles=5.0,  # Eventbrite doesn't provide distance
        url=event.url,
    )


def _convert_exa_result(result: ExaSearchResult) -> EventResult:
    """Convert ExaSearchResult to EventResult format."""
    # Generate stable ID from URL
    event_id = hashlib.md5(result.url.encode()).hexdigest()[:12]

    # Extract date from result if available
    date_str = datetime.now().isoformat()
    if result.published_date:
        date_str = result.published_date.isoformat()

    # Use highlights for description, fall back to text snippet
    description = ""
    if result.highlights:
        description = " ".join(result.highlights[:2])
    elif result.text:
        description = result.text[:200]

    return EventResult(
        id=f"exa-{event_id}",
        title=result.title,
        date=date_str,
        location="Columbus, OH",  # Exa doesn't provide structured location
        category="community",  # Default category
        description=description,
        is_free=False,  # Unknown from Exa
        price_amount=None,
        distance_miles=10.0,  # Unknown from Exa
        url=result.url,
    )


def _normalize_url(url: str | None) -> str | None:
    """Normalize URL for deduplication."""
    if not url:
        return None

    parsed = urlparse(url)
    # Remove www., trailing slashes, query params for comparison
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def _normalize_title(title: str) -> str:
    """Normalize title for deduplication."""
    # Lowercase, remove punctuation, extra whitespace
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _deduplicate_events(events: list[EventResult]) -> list[EventResult]:
    """Remove duplicate events based on URL or title similarity."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique_events: list[EventResult] = []

    for event in events:
        # Check URL-based dedup
        normalized_url = _normalize_url(event.url)
        if normalized_url and normalized_url in seen_urls:
            continue

        # Check title-based dedup
        normalized_title = _normalize_title(event.title)
        if normalized_title in seen_titles:
            continue

        # Mark as seen
        if normalized_url:
            seen_urls.add(normalized_url)
        seen_titles.add(normalized_title)
        unique_events.append(event)

    return unique_events


def _convert_source_results(
    source_name: str, results: list[object]
) -> list[EventResult]:
    """Convert source-specific results to EventResult format."""
    events: list[EventResult] = []

    for result in results:
        try:
            if source_name == "eventbrite" and isinstance(result, EventbriteEvent):
                events.append(_convert_eventbrite_event(result))
            elif source_name == "exa" and isinstance(result, ExaSearchResult):
                events.append(_convert_exa_result(result))
            else:
                # Unknown source type - skip
                logger.debug("Skipping unknown result type from %s", source_name)
        except Exception as e:
            logger.warning("Error converting result from %s: %s", source_name, e)

    return events


async def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile.

    Uses the event source registry to query all enabled sources in parallel,
    then deduplicates results.

    Args:
        profile: SearchProfile with location, date_window, categories, constraints

    Returns:
        SearchResult with events list and source attribution
    """
    registry = get_event_source_registry()
    enabled_sources = registry.get_enabled()

    if not enabled_sources:
        # Fall back to settings check for backward compatibility
        settings = get_settings()
        if not settings.has_event_source:
            logger.warning("No event sources enabled in registry")
            return SearchResult(
                events=[],
                source="unavailable",
                message="Event search is not currently available.",
            )

    try:
        # Build list of fetch tasks from enabled sources
        tasks = []
        source_names = []

        for source in enabled_sources:
            tasks.append(source.search_fn(profile))
            source_names.append(source.name)

        if not tasks:
            return SearchResult(
                events=[],
                source="unavailable",
                message="No event sources are currently enabled.",
            )

        # Query sources in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect events from successful fetches
        all_events: list[EventResult] = []
        successful_sources: list[str] = []

        for i, result in enumerate(results):
            source_name = source_names[i]
            if isinstance(result, BaseException):
                logger.warning("%s fetch failed: %s", source_name, result)
            elif isinstance(result, list):
                # Convert source-specific results to EventResult
                converted = _convert_source_results(source_name, result)
                if converted:
                    all_events.extend(converted)
                    successful_sources.append(source_name)
                    logger.info("%s returned %d events", source_name, len(converted))

        if not all_events:
            source = "+".join(successful_sources) if successful_sources else "unavailable"
            return SearchResult(
                events=[],
                source=source,
                message="No events found matching your criteria. Try broadening your search.",
            )

        # Deduplicate merged results
        unique_events = _deduplicate_events(all_events)
        logger.info(
            "Merged %d events from %s, %d after dedup",
            len(all_events),
            "+".join(successful_sources),
            len(unique_events),
        )

        # Sort by date
        unique_events.sort(key=lambda e: e.date)

        return SearchResult(
            events=unique_events,
            source="+".join(successful_sources),
            message=None,
        )

    except Exception as e:
        logger.error("Multi-source search error: %s", e, exc_info=True)
        return SearchResult(
            events=[],
            source="unavailable",
            message="Event search encountered an error. Please try again.",
        )


def refine_results(input_data: RefinementInput) -> RefinementOutput:
    """
    Refine search results based on user feedback.

    Args:
        input_data: Contains feedback list with user ratings and reasons

    Returns:
        Refined events and explanation of changes
    """
    feedback = input_data.feedback

    # Analyze feedback to understand preferences
    wants_closer = False
    wants_cheaper = False
    wants_different_type = False
    liked_ids = []

    for fb in feedback:
        if fb.rating.value == "no" and fb.reason:
            reason_lower = fb.reason.lower()
            if "far" in reason_lower or "distance" in reason_lower:
                wants_closer = True
            elif (
                "expensive" in reason_lower
                or "cost" in reason_lower
                or "price" in reason_lower
            ):
                wants_cheaper = True
            elif "vibe" in reason_lower or "type" in reason_lower or "category" in reason_lower:
                wants_different_type = True
        elif fb.rating.value == "yes":
            liked_ids.append(fb.event_id)

    # Generate explanation
    explanation_parts = []
    if wants_closer:
        explanation_parts.append("looking for closer events")
    if wants_cheaper:
        explanation_parts.append("filtering to free or cheaper options")
    if wants_different_type:
        explanation_parts.append("exploring different event types")
    if liked_ids:
        explanation_parts.append(f"noting your interest in {len(liked_ids)} event(s)")

    if explanation_parts:
        explanation = "Based on your feedback, I'm " + " and ".join(explanation_parts) + "."
    else:
        explanation = "I've noted your preferences."

    # Refinement always returns unavailable since we don't yet have real-time search refinement
    return RefinementOutput(
        events=[],
        explanation=(
            f"{explanation} However, I don't have additional events to show right now. "
            "Would you like to start a new search with different criteria?"
        ),
        source="unavailable",
    )


SEARCH_AGENT_INSTRUCTIONS = """You show search results and help users refine them based on their feedback.

## Your Role
You're a helpful events concierge. Present results clearly and learn from user preferences to improve recommendations.

## CRITICAL GROUNDING RULES

1. **Source Attribution**: Always check the `source` field from search results:
   - If source is "unavailable": Say "I'm sorry, event search isn't available right now. Please try again later."
   - If source is "eventbrite": Present events normally without qualification.

2. **Zero Results**: If the events list is empty:
   - DO NOT invent events
   - DO NOT claim there are events when there aren't
   - Say "I couldn't find any events matching your criteria" and suggest broadening the search

3. **No Fabrication**:
   - NEVER make up event names, dates, locations, or URLs
   - NEVER guess at event details not in the data
   - If a field is missing, say "details not available"

4. **Message Handling**: If the result includes a `message` field, incorporate it naturally in your response.

## Flow

1. **Present Results** - When you receive a SearchProfile, use the search_events tool to find events
   - Show 3-5 events at a time
   - For each event include: title, date/time, location, category, price
   - Keep descriptions brief but informative
   - Include the event URL if available

2. **Gather Feedback** - Ask the user to rate the events
   - Accept: Yes (interested), No (not interested), Maybe (could work)
   - Ask for reasons on "No" votes: too far? too expensive? wrong vibe?
   - Reasons help you refine better

3. **Refine Results** - Use refine_results tool with feedback
   - Explain what changed: "I'm showing closer events since you said X was too far"
   - Present the refined results

4. **Iterate** - Continue until user is satisfied or says they're done
   - If they say "that's good" or pick events, wrap up
   - If they want more options, keep refining

## Presentation Format

```
Here's what I found:

1. **Event Title** - Day, Time
   Venue Name (distance) | Category | Price
   Brief description
   [Link to event]

2. ...
```

What do you think? Let me know which ones interest you (or not)!

## Example Feedback Handling

User: "The first one looks good, but the second is too far"
You: "Got it! I'll note your interest in the first event and look for closer alternatives."
[Uses refine_results with feedback]
"Based on your feedback, I found some closer options..."
"""

search_events_tool = function_tool(search_events)
refine_results_tool = function_tool(refine_results)

search_agent = Agent(
    name="SearchAgent",
    instructions=SEARCH_AGENT_INSTRUCTIONS,
    model="gpt-4o",
    tools=[search_events_tool, refine_results_tool],
)
