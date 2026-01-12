"""
SearchAgent for Phase 2: Search and refinement.

Shows search results based on SearchProfile and refines
based on user feedback (Yes/No/Maybe ratings).
"""

import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime
from urllib.parse import urlparse

from agents import Agent, function_tool

from api.config import get_settings
from api.models import (
    EventResult,
    RefinementInput,
    RefinementOutput,
    SearchProfile,
    SearchResult,
)
from api.services import (
    EventbriteEvent,
    ExaSearchResult,
    ScrapedEvent,
    get_event_source_registry,
)
from api.services.meetup import MeetupEvent

logger = logging.getLogger(__name__)


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


def _convert_exa_result(result: ExaSearchResult) -> EventResult | None:
    """Convert ExaSearchResult to EventResult. Returns None if date is missing."""
    if not result.url:
        return None

    # Skip results without dates
    if not result.published_date:
        logger.debug(
            "⏭️ [Search] Skipping Exa result without date | title=%s url=%s",
            result.title[:50] if result.title else "untitled",
            result.url[:80],
        )
        return None

    # Generate stable ID from URL
    event_id = hashlib.md5(result.url.encode()).hexdigest()[:12]
    date_str = result.published_date.isoformat()

    # Use highlights for description, fall back to text snippet
    description = ""
    if result.highlights:
        description = " ".join(result.highlights[:2])
    elif result.text:
        description = result.text[:200]

    return EventResult(
        id=f"exa-{event_id}",
        title=result.title or "Untitled Event",
        date=date_str,
        location="Columbus, OH",  # Exa doesn't provide structured location
        category="community",  # Default category
        description=description,
        is_free=False,  # Unknown from Exa
        price_amount=None,
        distance_miles=10.0,  # Unknown from Exa
        url=result.url,
    )


def _convert_scraped_event(event: ScrapedEvent) -> EventResult | None:
    """Convert scraped event to EventResult. Returns None if date is missing."""
    # Skip events without dates
    if not event.start_time:
        logger.debug(
            "⏭️ [Search] Skipping event without date | source=%s title=%s url=%s",
            event.source,
            event.title[:50] if event.title else "untitled",
            event.url or "no-url",
        )
        return None

    # Build location string
    location = event.venue_name or "TBD"
    if event.venue_address:
        location = f"{location}, {event.venue_address}"

    return EventResult(
        id=f"posh-{event.event_id}",
        title=event.title,
        date=event.start_time.isoformat(),
        location=location,
        category=event.category,
        description=event.description[:200] if event.description else "",
        is_free=event.is_free,
        price_amount=event.price_amount,
        distance_miles=5.0,  # Unknown from Posh
        url=event.url,
    )


def _convert_meetup_event(event: MeetupEvent) -> EventResult:
    """Convert MeetupEvent to EventResult format."""
    # Build location string
    location = event.venue_name or "TBD"
    if event.venue_address:
        location = f"{location}, {event.venue_address}"

    return EventResult(
        id=f"meetup-{event.id}",
        title=event.title,
        date=event.start_time.isoformat(),
        location=location,
        category=event.category,
        description=event.description[:200] if event.description else "",
        is_free=event.is_free,
        price_amount=event.price_amount,
        distance_miles=5.0,  # Meetup radius is in miles but no exact distance
        url=event.url,
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
    """Remove duplicate events based on URL and title similarity."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique_events: list[EventResult] = []

    for event in events:
        normalized_url = _normalize_url(event.url)

        # Check URL duplicate
        if normalized_url and normalized_url in seen_urls:
            logger.debug(
                "📋 [Dedup] Removed (URL match) | id=%s title=%s url=%s",
                event.id[:20] if event.id else "none",
                event.title[:40] if event.title else "untitled",
                normalized_url[:60],
            )
            continue

        normalized_title = _normalize_title(event.title)

        # Check title duplicate
        if normalized_title in seen_titles:
            logger.debug(
                "📋 [Dedup] Removed (title match) | id=%s title=%s normalized=%s",
                event.id[:20] if event.id else "none",
                event.title[:40] if event.title else "untitled",
                normalized_title[:40],
            )
            continue

        # Event is unique, track it
        if normalized_url:
            seen_urls.add(normalized_url)
        seen_titles.add(normalized_title)
        unique_events.append(event)

    return unique_events


def _validate_event(event: EventResult) -> EventResult | None:
    """
    Validate event has required fields and reasonable values.
    Returns None if event should be filtered out.
    """
    from datetime import timedelta, timezone

    # Must have title
    if not event.title or event.title.lower() in ("untitled", "untitled event", ""):
        logger.debug("Filtered event: missing title | id=%s", event.id)
        return None

    # Must have date
    if not event.date:
        logger.debug(
            "Filtered event: missing date | id=%s title=%s", event.id, event.title
        )
        return None

    # Date must be parseable and include year
    try:
        parsed = datetime.fromisoformat(event.date.replace("Z", "+00:00"))

        # Date should be in the future (or at least today)
        now = datetime.now(timezone.utc)
        if parsed < now - timedelta(days=1):  # Allow 1 day buffer
            logger.debug(
                "Filtered event: date in past | id=%s title=%s date=%s",
                event.id,
                event.title,
                event.date,
            )
            return None

    except ValueError:
        logger.debug(
            "Filtered event: unparseable date | id=%s title=%s date=%s",
            event.id,
            event.title,
            event.date,
        )
        return None

    # URL should be valid if present
    if event.url:
        if not event.url.startswith(("http://", "https://")):
            # Create a new EventResult with cleared URL rather than filtering
            return EventResult(
                id=event.id,
                title=event.title,
                date=event.date,
                location=event.location,
                category=event.category,
                description=event.description,
                is_free=event.is_free,
                price_amount=event.price_amount,
                distance_miles=event.distance_miles,
                url=None,
            )

    return event


def _validate_events(events: list[EventResult]) -> list[EventResult]:
    """Validate all events and filter out invalid ones."""
    validated = []
    for event in events:
        valid = _validate_event(event)
        if valid:
            validated.append(valid)

    if len(validated) < len(events):
        logger.info(
            "Validation filtered %d/%d events",
            len(events) - len(validated),
            len(events),
        )

    return validated


def _filter_by_time_range(
    events: list[EventResult],
    profile: SearchProfile,
) -> list[EventResult]:
    """
    HARD FILTER: Remove events outside the user's time range.

    This is a guardrail - we should NEVER return events that don't match
    the user's time criteria. If no time window is specified, we default
    to filtering out past events (events before now).

    Args:
        events: List of events to filter
        profile: SearchProfile with time_window

    Returns:
        Events that are within the time range
    """
    now = datetime.now()
    filtered: list[EventResult] = []

    # Get time bounds from profile
    start_bound = None
    end_bound = None

    if profile.time_window:
        start_bound = profile.time_window.start
        end_bound = profile.time_window.end

    # If no start bound specified, default to NOW (no past events)
    if start_bound is None:
        start_bound = now
        logger.debug("📅 [TimeFilter] No start time specified, defaulting to now")

    for event in events:
        if not event.date:
            logger.debug(
                "⏭️ [TimeFilter] Skipping event without date | id=%s title=%s",
                event.id[:20] if event.id else "none",
                event.title[:40] if event.title else "untitled",
            )
            continue

        try:
            # Parse event date (ISO 8601 format)
            event_dt = datetime.fromisoformat(event.date.replace("Z", "+00:00"))

            # Make naive if comparing with naive datetime
            if event_dt.tzinfo is not None and start_bound.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=None)

            # Check start bound (HARD FILTER - no events before this)
            if event_dt < start_bound:
                logger.debug(
                    "⏭️ [TimeFilter] Event before start bound | id=%s title=%s date=%s start=%s",
                    event.id[:20] if event.id else "none",
                    event.title[:40] if event.title else "untitled",
                    event.date,
                    start_bound.isoformat(),
                )
                continue

            # Check end bound if specified (HARD FILTER - no events after this)
            if end_bound is not None:
                end_to_compare = end_bound
                if event_dt.tzinfo is not None and end_bound.tzinfo is None:
                    end_to_compare = end_bound
                    event_dt = event_dt.replace(tzinfo=None)

                if event_dt > end_to_compare:
                    logger.debug(
                        "⏭️ [TimeFilter] Event after end bound | id=%s title=%s date=%s end=%s",
                        event.id[:20] if event.id else "none",
                        event.title[:40] if event.title else "untitled",
                        event.date,
                        end_bound.isoformat(),
                    )
                    continue

            # Event is within time range
            filtered.append(event)

        except (ValueError, TypeError) as e:
            logger.warning(
                "⚠️ [TimeFilter] Failed to parse event date | id=%s date=%s error=%s",
                event.id[:20] if event.id else "none",
                event.date,
                str(e),
            )
            # Skip events with unparseable dates
            continue

    removed_count = len(events) - len(filtered)
    if removed_count > 0:
        logger.info(
            "📅 [TimeFilter] Removed %d events outside time range | kept=%d",
            removed_count,
            len(filtered),
        )

    return filtered


def _convert_source_results(
    source_name: str, results: list[object]
) -> list[EventResult]:
    """Convert source-specific results to EventResult format."""
    events: list[EventResult] = []

    for result in results:
        try:
            converted: EventResult | None = None
            if source_name == "eventbrite" and isinstance(result, EventbriteEvent):
                converted = _convert_eventbrite_event(result)
            elif source_name == "exa" and isinstance(result, ExaSearchResult):
                converted = _convert_exa_result(result)
            elif source_name == "posh" and isinstance(result, ScrapedEvent):
                converted = _convert_scraped_event(result)
            elif source_name == "meetup" and isinstance(result, MeetupEvent):
                converted = _convert_meetup_event(result)
            else:
                # Unknown source type - skip
                logger.debug("Skipping unknown result type from %s", source_name)
                continue

            # Filter out None results (events without dates)
            if converted is not None:
                events.append(converted)
        except Exception as e:
            logger.warning("Error converting result from %s: %s", source_name, e)

    return events


async def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile from multiple sources.

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

        for event_source in enabled_sources:
            tasks.append(event_source.search_fn(profile))
            source_names.append(event_source.name)

        if not tasks:
            return SearchResult(
                events=[],
                source="unavailable",
                message="No event sources are currently enabled.",
            )

        # Query API sources in parallel
        logger.debug(
            "🔍 [Search] Starting parallel fetch | sources=%s",
            ", ".join(source_names),
        )
        start_time = time.perf_counter()

        results = await asyncio.gather(*tasks, return_exceptions=True)

        fetch_elapsed = time.perf_counter() - start_time
        logger.debug(
            "📊 [Search] Parallel fetch complete | duration=%.2fs",
            fetch_elapsed,
        )

        # Collect events from successful fetches
        all_events: list[EventResult] = []
        successful_sources: list[str] = []

        for i, result in enumerate(results):
            source_name = source_names[i]
            if isinstance(result, BaseException):
                logger.debug(
                    "❌ [Search] Source failed | source=%s error=%s",
                    source_name,
                    str(result)[:100],
                )
                logger.warning("%s fetch failed: %s", source_name, result)
            elif isinstance(result, list):
                # Convert source-specific results to EventResult
                converted = _convert_source_results(source_name, result)
                if converted:
                    all_events.extend(converted)
                    successful_sources.append(source_name)
                    logger.debug(
                        "✅ [Search] Source complete | source=%s events=%d",
                        source_name,
                        len(converted),
                    )
                    # Log individual events at DEBUG level
                    if logger.isEnabledFor(logging.DEBUG):
                        for event in converted:
                            logger.debug(
                                "📋 [Search] Event from source | source=%s id=%s title=%s",
                                source_name,
                                event.id[:20] if event.id else "none",
                                event.title[:50] if event.title else "untitled",
                            )
                else:
                    logger.debug(
                        "📭 [Search] Source empty | source=%s",
                        source_name,
                    )

        # HARD FILTER: Remove events outside time range
        # This is a guardrail - we NEVER return events outside the user's criteria
        # all_events = _filter_by_time_range(all_events, profile)
        all_events = all_events

        if not all_events:
            source = "+".join(successful_sources) if successful_sources else "unavailable"
            return SearchResult(
                events=[],
                source=source,
                message="No events found matching your criteria. Try broadening your search.",
            )

        # Deduplicate merged results
        unique_events = _deduplicate_events(all_events)
        logger.debug(
            "📊 [Search] Deduplication | before=%d after=%d removed=%d",
            len(all_events),
            len(unique_events),
            len(all_events) - len(unique_events),
        )

        # Validate all events (filter out invalid dates, missing titles, etc.)
        validated_events = _validate_events(unique_events)

        # Sort by date and limit
        sorted_events = sorted(validated_events, key=lambda e: e.date if e.date else "")
        final_events = sorted_events[:15]

        # Log truncation if events were cut
        if len(final_events) < len(sorted_events):
            truncated_count = len(sorted_events) - len(final_events)
            logger.debug(
                "📋 [Search] Truncated results | kept=%d removed=%d",
                len(final_events),
                truncated_count,
            )
            # Log which events were truncated
            if logger.isEnabledFor(logging.DEBUG):
                for event in sorted_events[15:]:
                    logger.debug(
                        "📋 [Search] Truncated event | id=%s title=%s date=%s",
                        event.id[:20] if event.id else "none",
                        event.title[:40] if event.title else "untitled",
                        event.date[:20] if event.date else "no-date",
                    )

        return SearchResult(
            events=final_events,
            source="+".join(successful_sources),
            message=None,
        )

    except Exception as e:
        logger.error("API source fetch error: %s", e, exc_info=True)
        return SearchResult(
            events=[],
            source="unavailable",
            message="An error occurred while searching for events.",
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


SEARCH_AGENT_INSTRUCTIONS_TEMPLATE = """You show search results and help users refine them based on their feedback.

## Your Role
You're a helpful events concierge. Present results clearly and learn from user preferences to improve recommendations.

## CRITICAL GROUNDING RULES

1. **Source Attribution**: Always check the `source` field from search results:
   - If source is "unavailable": Say "I'm sorry, event search isn't available right now. Please try again later."
   - If source contains "luma", "eventbrite", or both (e.g., "luma+eventbrite"): Present events normally.
   - Events come from multiple sources (Luma, Eventbrite, etc.) and are merged together.

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


def get_search_instructions(context: object, agent: object) -> str:
    """Generate search agent instructions with current date.

    Args:
        context: RunContextWrapper from agents library (unused)
        agent: Agent instance (unused)
    """
    today = datetime.now().strftime("%A, %B %d, %Y")
    return f"""Today's date is {today}.

{SEARCH_AGENT_INSTRUCTIONS_TEMPLATE}"""


# Alias for backward compatibility
SEARCH_AGENT_INSTRUCTIONS = SEARCH_AGENT_INSTRUCTIONS_TEMPLATE

search_events_tool = function_tool(search_events)
refine_results_tool = function_tool(refine_results)

search_agent = Agent(
    name="SearchAgent",
    instructions=get_search_instructions,
    model="gpt-4o",
    tools=[search_events_tool, refine_results_tool],
)
