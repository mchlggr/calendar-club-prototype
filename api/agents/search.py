"""
SearchAgent for Phase 2: Search and refinement.

Shows search results based on SearchProfile and refines
based on user feedback (Yes/No/Maybe ratings).

Production Behavior:
- DEMO_MODE=true: Returns sample events clearly labeled as demo data
- DEMO_MODE=false (default): Requires EVENTBRITE_API_KEY for real events
- Without API key and DEMO_MODE=false: Returns unavailable status
"""

import asyncio
import os
from enum import Enum

from pydantic import BaseModel, Field

from agents import Agent, function_tool

from api.models import EventFeedback, SearchProfile
from api.services import get_eventbrite_client

# Environment configuration
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"


class DataSource(str, Enum):
    """Source of event data."""

    EVENTBRITE = "eventbrite"
    DEMO = "demo"
    UNAVAILABLE = "unavailable"


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


class SearchResult(BaseModel):
    """Result from search_events with source attribution."""

    events: list[EventResult]
    source: DataSource
    message: str = Field(description="Human-readable message about the data source")


class RefinementInput(BaseModel):
    """Input for refine_results tool."""

    feedback: list[EventFeedback] = Field(description="User feedback on events")


class RefinementOutput(BaseModel):
    """Output from refine_results tool with source attribution."""

    events: list[EventResult]
    explanation: str
    source: DataSource
    can_refine: bool = Field(
        description="Whether refinement is possible with current data source"
    )


def _get_demo_events() -> list[EventResult]:
    """Return demo events for DEMO_MODE - clearly labeled as sample data."""
    return [
        EventResult(
            id="demo-001",
            title="[DEMO] Columbus AI Meetup",
            date="2026-01-10T18:00:00",
            location="Industrious Columbus",
            category="ai",
            description="Monthly AI/ML practitioners meetup (demo event)",
            is_free=True,
            price_amount=None,
            distance_miles=2.5,
            url="https://example.com/demo/ai-meetup",
        ),
        EventResult(
            id="demo-002",
            title="[DEMO] Startup Weekend Columbus",
            date="2026-01-11T09:00:00",
            location="Rev1 Ventures",
            category="startup",
            description="54-hour startup creation event (demo event)",
            is_free=False,
            price_amount=75,
            distance_miles=3.1,
            url="https://example.com/demo/startup-weekend",
        ),
        EventResult(
            id="demo-003",
            title="[DEMO] Tech on Tap",
            date="2026-01-10T17:30:00",
            location="Land-Grant Brewing",
            category="community",
            description="Casual tech networking over beers (demo event)",
            is_free=True,
            price_amount=None,
            distance_miles=1.8,
            url="https://example.com/demo/tech-on-tap",
        ),
    ]


async def _fetch_eventbrite_events(profile: SearchProfile) -> list[EventResult]:
    """Fetch events from Eventbrite API."""
    client = get_eventbrite_client()

    # Extract search parameters from profile
    location = profile.location or "Columbus, OH"
    categories = [c.value for c in profile.categories] if profile.categories else None
    free_only = profile.constraints.free_only if profile.constraints else False

    # Parse date window
    start_date = None
    end_date = None
    if profile.date_window:
        start_date = profile.date_window.start
        end_date = profile.date_window.end

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


@function_tool
def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile.

    Args:
        profile: SearchProfile with location, date_window, categories, constraints

    Returns:
        SearchResult with events, data source, and message about source
    """
    # Demo mode: return sample events with clear labeling
    if DEMO_MODE:
        return SearchResult(
            events=_get_demo_events(),
            source=DataSource.DEMO,
            message="These are sample events for demonstration purposes. "
            "Real event data is not currently available.",
        )

    # Production mode: require API key
    if not os.getenv("EVENTBRITE_API_KEY"):
        return SearchResult(
            events=[],
            source=DataSource.UNAVAILABLE,
            message="Event search is currently unavailable. "
            "Please try again later or contact support.",
        )

    try:
        # Run async fetch in sync context (tool functions are sync)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, _fetch_eventbrite_events(profile)
                )
                events = future.result(timeout=30)
        else:
            events = loop.run_until_complete(_fetch_eventbrite_events(profile))

        if events:
            return SearchResult(
                events=events,
                source=DataSource.EVENTBRITE,
                message=f"Found {len(events)} events from Eventbrite.",
            )
        else:
            return SearchResult(
                events=[],
                source=DataSource.EVENTBRITE,
                message="No events found matching your criteria. "
                "Try broadening your search.",
            )

    except Exception as e:
        # Log error but don't expose internal details
        print(f"Eventbrite API error: {e}")
        return SearchResult(
            events=[],
            source=DataSource.UNAVAILABLE,
            message="Event search encountered an error. Please try again later.",
        )


@function_tool
def refine_results(input_data: RefinementInput) -> RefinementOutput:
    """
    Refine search results based on user feedback.

    Args:
        input_data: Contains feedback list with user ratings and reasons

    Returns:
        RefinementOutput with refined events, explanation, and source
    """
    feedback = input_data.feedback

    # Analyze feedback to build explanation
    wants_closer = False
    wants_cheaper = False
    wants_different_type = False
    liked_ids: list[str] = []

    for fb in feedback:
        if fb.rating.value == "no" and fb.reason:
            reason_lower = fb.reason.lower()
            if "far" in reason_lower or "distance" in reason_lower:
                wants_closer = True
            elif "expensive" in reason_lower or "price" in reason_lower or "cost" in reason_lower:
                wants_cheaper = True
            elif "vibe" in reason_lower or "type" in reason_lower:
                wants_different_type = True
        elif fb.rating.value == "yes":
            liked_ids.append(fb.event_id)

    # Build explanation
    explanation_parts = []
    if wants_closer:
        explanation_parts.append("looking for closer events")
    if wants_cheaper:
        explanation_parts.append("filtering to more affordable options")
    if wants_different_type:
        explanation_parts.append("exploring different event types")
    if liked_ids:
        explanation_parts.append(f"noting your interest in {len(liked_ids)} event(s)")

    base_explanation = (
        "Based on your feedback, I'm " + " and ".join(explanation_parts) + "."
        if explanation_parts
        else "I've noted your preferences."
    )

    # Demo mode: return demo events with clear labeling
    if DEMO_MODE:
        demo_events = [
            EventResult(
                id="demo-refined-001",
                title="[DEMO] Python Columbus",
                date="2026-01-10T18:30:00",
                location="CoverMyMeds HQ",
                category="ai",
                description="Python user group with AI/ML focus (demo event)",
                is_free=True,
                price_amount=None,
                distance_miles=1.2,
                url="https://example.com/demo/python-columbus",
            ),
            EventResult(
                id="demo-refined-002",
                title="[DEMO] Data Science Happy Hour",
                date="2026-01-10T17:00:00",
                location="Brewdog Short North",
                category="ai",
                description="Informal data science networking (demo event)",
                is_free=True,
                price_amount=None,
                distance_miles=0.8,
                url="https://example.com/demo/data-science-happy-hour",
            ),
        ]
        return RefinementOutput(
            events=demo_events,
            explanation=base_explanation + " Here are some sample refined results (demo data).",
            source=DataSource.DEMO,
            can_refine=True,
        )

    # Production mode: cannot refine without re-querying API
    return RefinementOutput(
        events=[],
        explanation=base_explanation + " To find better matches, please start a new search "
        "with updated preferences. Real-time refinement requires a new search query.",
        source=DataSource.UNAVAILABLE,
        can_refine=False,
    )


SEARCH_AGENT_INSTRUCTIONS = """You show search results and help users refine them based on their feedback.

## Your Role
You're a helpful events concierge. Present results clearly and learn from user preferences to improve recommendations.

## CRITICAL RULES - Grounded Behavior

1. **Source Attribution**: ALWAYS mention where events come from based on the `source` field:
   - "eventbrite": "Here are real events from Eventbrite..."
   - "demo": "These are sample events for demonstration..."
   - "unavailable": Be honest that search is currently unavailable

2. **Never Fabricate**: Only present events returned by the search_events tool. Never make up event names, dates, or details.

3. **Empty Results**: If search returns no events, say so honestly. Suggest broadening the search or trying different criteria.

4. **Refinement Limits**: If refine_results returns can_refine=false, explain that a new search is needed rather than pretending to refine.

## Flow

1. **Present Results** - When you receive a SearchProfile, use the search_events tool to find events
   - Check the `source` field and mention it to the user
   - Show 3-5 events at a time
   - For each event include: title, date/time, location, category, price
   - Keep descriptions brief but informative

2. **Handle Source Types**:
   - EVENTBRITE: "Here are real events I found..."
   - DEMO: "These are sample events for demonstration. In production, you'd see real events here."
   - UNAVAILABLE: "I'm sorry, event search is temporarily unavailable. Please try again later."

3. **Gather Feedback** - Ask the user to rate the events
   - Accept: Yes (interested), No (not interested), Maybe (could work)
   - Ask for reasons on "No" votes: too far? too expensive? wrong vibe?
   - Reasons help you refine better

4. **Refine Results** - Use refine_results tool with feedback
   - Check can_refine field - if false, suggest a new search instead
   - Explain what changed based on their feedback
   - Present the refined results with source attribution

5. **Iterate** - Continue until user is satisfied or says they're done
   - If they say "that's good" or pick events, wrap up
   - If they want more options and can_refine is false, suggest starting a new search

## Presentation Format

```
Here's what I found from [source]:

1. **Columbus AI Meetup** - Friday 6pm
   Industrious Columbus (2.5 mi) | AI/Tech | Free
   Monthly AI/ML practitioners meetup

2. **Tech on Tap** - Friday 5:30pm
   Land-Grant Brewing (1.8 mi) | Community | Free
   Casual tech networking over beers

What do you think? Let me know which ones interest you (or not)!
```

## Example Feedback Handling

User: "The first one looks good, but the second is too far"
You: "Got it! I'll note your interest in the AI Meetup and look for closer alternatives."
[Uses refine_results with feedback, checks can_refine]
If can_refine=true: "Based on your feedback, I found some closer options..."
If can_refine=false: "I've noted your preferences. To find closer events, let's start a new search..."
"""

search_agent = Agent(
    name="SearchAgent",
    instructions=SEARCH_AGENT_INSTRUCTIONS,
    model="gpt-4o",
    tools=[search_events, refine_results],
)
