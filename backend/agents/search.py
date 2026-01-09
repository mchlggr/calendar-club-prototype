"""
SearchAgent for Phase 2: Search and refinement.

Shows search results based on SearchProfile and refines
based on user feedback (Yes/No/Maybe ratings).
"""

from pydantic import BaseModel, Field

from agents import Agent, function_tool

from backend.models import EventFeedback, SearchProfile


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


class RefinementInput(BaseModel):
    """Input for refine_results tool."""

    feedback: list[EventFeedback] = Field(description="User feedback on events")


class RefinementOutput(BaseModel):
    """Output from refine_results tool."""

    events: list[EventResult]
    explanation: str


@function_tool
def search_events(profile: SearchProfile) -> list[EventResult]:
    """
    Search for events matching the profile.

    Args:
        profile: SearchProfile with location, date_window, categories, constraints

    Returns:
        List of events matching the search criteria
    """
    # TODO: Implement actual search against event sources
    # For now, return mock data to enable end-to-end testing
    _ = profile  # Will be used when real search is implemented
    return [
        EventResult(
            id="evt-001",
            title="Columbus AI Meetup",
            date="2026-01-10T18:00:00",
            location="Industrious Columbus",
            category="ai",
            description="Monthly AI/ML practitioners meetup",
            is_free=True,
            price_amount=None,
            distance_miles=2.5,
        ),
        EventResult(
            id="evt-002",
            title="Startup Weekend Columbus",
            date="2026-01-11T09:00:00",
            location="Rev1 Ventures",
            category="startup",
            description="54-hour startup creation event",
            is_free=False,
            price_amount=75,
            distance_miles=3.1,
        ),
        EventResult(
            id="evt-003",
            title="Tech on Tap",
            date="2026-01-10T17:30:00",
            location="Land-Grant Brewing",
            category="community",
            description="Casual tech networking over beers",
            is_free=True,
            price_amount=None,
            distance_miles=1.8,
        ),
    ]


@function_tool
def refine_results(input_data: RefinementInput) -> RefinementOutput:
    """
    Refine search results based on user feedback.

    Args:
        input_data: Contains feedback list with user ratings and reasons

    Returns:
        Refined events and explanation of changes
    """
    feedback = input_data.feedback

    # Build constraints from feedback
    constraints = []
    preferences = []

    for fb in feedback:
        if fb.rating.value == "no" and fb.reason:
            reason_lower = fb.reason.lower()
            if "far" in reason_lower:
                constraints.append("closer events")
            elif "expensive" in reason_lower:
                constraints.append("free or cheaper events")
            elif "vibe" in reason_lower or "type" in reason_lower:
                constraints.append("different event types")
        elif fb.rating.value == "yes":
            preferences.append(fb.event_id)

    # Generate explanation
    explanation_parts = []
    if "closer events" in constraints:
        explanation_parts.append("showing closer events")
    if "free or cheaper events" in constraints:
        explanation_parts.append("filtering to free/cheaper options")
    if preferences:
        explanation_parts.append("prioritizing similar events to ones you liked")

    explanation = (
        "Based on your feedback, I'm " + " and ".join(explanation_parts) + "."
        if explanation_parts
        else "Here are some alternative suggestions based on your preferences."
    )

    # Return refined results (simplified - real implementation would re-query)
    # For now, return the same mock events
    events = [
        EventResult(
            id="evt-004",
            title="Python Columbus",
            date="2026-01-10T18:30:00",
            location="CoverMyMeds HQ",
            category="ai",
            description="Python user group with AI/ML focus",
            is_free=True,
            price_amount=None,
            distance_miles=1.2,
        ),
        EventResult(
            id="evt-005",
            title="Data Science Happy Hour",
            date="2026-01-10T17:00:00",
            location="Brewdog Short North",
            category="ai",
            description="Informal data science networking",
            is_free=True,
            price_amount=None,
            distance_miles=0.8,
        ),
    ]

    return RefinementOutput(events=events, explanation=explanation)


SEARCH_AGENT_INSTRUCTIONS = """You show search results and help users refine them based on their feedback.

## Your Role
You're a helpful events concierge. Present results clearly and learn from user preferences to improve recommendations.

## Flow

1. **Present Results** - When you receive a SearchProfile, use the search_events tool to find events
   - Show 3-5 events at a time
   - For each event include: title, date/time, location, category, price
   - Keep descriptions brief but informative

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
You: "Got it! I'll note your interest in the AI Meetup and look for closer alternatives to Tech on Tap."
[Uses refine_results with feedback]
"Based on your feedback, I found some closer options..."
"""

search_agent = Agent(
    name="SearchAgent",
    instructions=SEARCH_AGENT_INSTRUCTIONS,
    model="gpt-4o",
    tools=[search_events, refine_results],
)
