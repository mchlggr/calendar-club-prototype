"""
SearchAgent for Phase 2: Search and refinement.

Shows search results based on SearchProfile and refines
based on user feedback (Yes/No/Maybe ratings).
"""

import asyncio
import logging
from datetime import datetime

from pydantic import BaseModel, Field

from agents import Agent, function_tool

from api.config import get_settings
from api.models import EventFeedback, SearchProfile
from api.services import get_eventbrite_client

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
        default="refined", description="Data source: 'refined', 'demo', or 'unavailable'"
    )


class SearchResult(BaseModel):
    """Result from search_events tool."""

    events: list[EventResult]
    source: str = Field(description="Data source: 'eventbrite', 'demo', or 'unavailable'")
    message: str | None = Field(
        default=None, description="User-facing message about data source"
    )


def _get_mock_events() -> list[EventResult]:
    """Return sample events for demo mode."""
    return [
        EventResult(
            id="evt-001",
            title="Sample: Columbus AI Meetup",
            date="2026-01-10T18:00:00",
            location="Demo Venue, Columbus, OH",
            category="ai",
            description="[Demo] Monthly AI/ML practitioners meetup",
            is_free=True,
            price_amount=None,
            distance_miles=2.5,
            url=None,
        ),
        EventResult(
            id="evt-002",
            title="Sample: Tech on Tap",
            date="2026-01-11T17:30:00",
            location="Demo Brewery, Columbus, OH",
            category="community",
            description="[Demo] Casual tech networking over drinks",
            is_free=True,
            price_amount=None,
            distance_miles=1.8,
            url=None,
        ),
        EventResult(
            id="evt-003",
            title="Sample: Startup Founders Circle",
            date="2026-01-12T08:30:00",
            location="Demo Co-working Space, Columbus, OH",
            category="startup",
            description="[Demo] Peer roundtable for early-stage founders",
            is_free=False,
            price_amount=20,
            distance_miles=3.1,
            url=None,
        ),
    ]


async def _fetch_eventbrite_events(profile: SearchProfile) -> list[EventResult]:
    """Fetch events from Eventbrite API."""
    client = get_eventbrite_client()

    # Extract search parameters from profile
    location = profile.location or "Columbus, OH"
    categories = profile.categories if profile.categories else None
    free_only = profile.free_only

    # Parse time window
    start_date: datetime | None = None
    end_date: datetime | None = None
    if profile.time_window:
        start_date = profile.time_window.start
        end_date = profile.time_window.end

    events = await client.search_events(
        location=location,
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        free_only=free_only,
        page_size=10,
    )

    # Convert to EventResult format
    results = []
    for event in events:
        venue = event.venue_name or "TBD"
        if event.venue_address:
            venue = f"{venue}, {event.venue_address}"

        results.append(
            EventResult(
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
        )

    return results


def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile.

    Args:
        profile: SearchProfile with location, date_window, categories, constraints

    Returns:
        SearchResult with events list and source attribution
    """
    settings = get_settings()

    # Check demo mode first
    if settings.demo_mode:
        logger.info("DEMO_MODE enabled - returning sample events")
        return SearchResult(
            events=_get_mock_events(),
            source="demo",
            message="Showing sample events (demo mode). These are examples, not real events.",
        )

    # Check for API key
    api_key = settings.eventbrite_api_key
    if not api_key:
        logger.warning("EVENTBRITE_API_KEY not configured and DEMO_MODE=false")
        return SearchResult(
            events=[],
            source="unavailable",
            message="Event search is not currently available. Please check back later.",
        )

    try:
        # Run async fetch in sync context (tool functions are sync)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, _fetch_eventbrite_events(profile)
                )
                events = future.result(timeout=30)
        else:
            events = loop.run_until_complete(_fetch_eventbrite_events(profile))

        if events:
            logger.info("Eventbrite returned %s events", len(events))
            return SearchResult(events=events, source="eventbrite", message=None)

        logger.info("Eventbrite returned no events for query")
        return SearchResult(
            events=[],
            source="eventbrite",
            message="No events found matching your criteria. Try broadening your search.",
        )

    except Exception as e:
        logger.error("Eventbrite API error: %s", e, exc_info=True)
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

    settings = get_settings()

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

    if not settings.demo_mode:
        return RefinementOutput(
            events=[],
            explanation=(
                f"{explanation} However, I don't have additional events to show right now. "
                "Would you like to start a new search with different criteria?"
            ),
            source="unavailable",
        )

    logger.info("DEMO_MODE: Returning sample refined events")
    demo_events = [
        EventResult(
            id="demo-refined-001",
            title="Sample: Python Columbus",
            date="2026-01-10T18:30:00",
            location="CoverMyMeds HQ",
            category="ai",
            description="[Demo] Python user group with AI/ML focus",
            is_free=True,
            price_amount=None,
            distance_miles=1.2,
            url=None,
        ),
        EventResult(
            id="demo-refined-002",
            title="Sample: Data Science Happy Hour",
            date="2026-01-10T17:00:00",
            location="Brewdog Short North",
            category="ai",
            description="[Demo] Informal data science networking",
            is_free=True,
            price_amount=None,
            distance_miles=0.8,
            url=None,
        ),
    ]

    return RefinementOutput(
        events=demo_events,
        explanation=explanation + " Here are some sample alternatives (demo mode).",
        source="demo",
    )


SEARCH_AGENT_INSTRUCTIONS = """You show search results and help users refine them based on their feedback.

## Your Role
You're a helpful events concierge. Present results clearly and learn from user preferences to improve recommendations.

## CRITICAL GROUNDING RULES

1. **Source Attribution**: Always check the `source` field from search results:
   - If source is "demo": Say "Here are some example events to show you how this works. These aren't real events."
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
