"""
SearchAgent for Phase 2: Results display and feedback collection.

Shows search results and refines recommendations based on
Yes/No/Maybe feedback from users.
"""

from typing import Union

from agents import Agent, function_tool

from backend.models import EventFeedback, Rating, SearchProfile


# Type definitions for events (will be expanded with actual event service)
class CalendarEvent:
    """Placeholder for calendar event data."""

    def __init__(
        self,
        event_id: str,
        title: str,
        date_time: str,
        location: str,
        category: str,
        distance_miles: Union[float, None] = None,
        price: Union[float, None] = None,
        description: str = "",
    ):
        self.event_id = event_id
        self.title = title
        self.date_time = date_time
        self.location = location
        self.category = category
        self.distance_miles = distance_miles
        self.price = price
        self.description = description

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "date_time": self.date_time,
            "location": self.location,
            "category": self.category,
            "distance_miles": self.distance_miles,
            "price": self.price,
            "description": self.description,
        }


@function_tool
def search_events(profile: SearchProfile) -> list[dict]:
    """
    Search for events matching the user's search profile.

    Args:
        profile: SearchProfile with location, date_window, categories, and constraints

    Returns:
        List of matching events with title, date/time, location, category, and metadata
    """
    # TODO: Integrate with actual event search service
    # For now, return mock data to enable development
    mock_events = [
        CalendarEvent(
            event_id="evt_001",
            title="Columbus AI Meetup: LLM Applications",
            date_time="2026-01-10T18:30:00-05:00",
            location="Improving Columbus, 21 E State St",
            category="ai",
            distance_miles=2.1,
            price=0,
            description="Monthly meetup discussing practical LLM applications",
        ),
        CalendarEvent(
            event_id="evt_002",
            title="Startup Grind: Founder Stories",
            date_time="2026-01-11T09:00:00-05:00",
            location="Rev1 Ventures, 1275 Kinnear Rd",
            category="startup",
            distance_miles=4.5,
            price=15,
            description="Breakfast event featuring local founder journeys",
        ),
        CalendarEvent(
            event_id="evt_003",
            title="Tech on Tap: Networking Happy Hour",
            date_time="2026-01-10T17:00:00-05:00",
            location="Seventh Son Brewing, 1101 N 4th St",
            category="community",
            distance_miles=1.8,
            price=0,
            description="Casual networking for Columbus tech professionals",
        ),
        CalendarEvent(
            event_id="evt_004",
            title="PyColumbus: Effect Systems in Python",
            date_time="2026-01-12T14:00:00-05:00",
            location="CoverMyMeds HQ, 2 Miranova Pl",
            category="ai",
            distance_miles=3.2,
            price=0,
            description="Deep dive into functional programming patterns",
        ),
        CalendarEvent(
            event_id="evt_005",
            title="Women in Tech Columbus",
            date_time="2026-01-11T12:00:00-05:00",
            location="The Junto, 546 E Main St",
            category="community",
            distance_miles=2.0,
            price=25,
            description="Monthly lunch and networking for women in tech",
        ),
    ]

    # Apply basic filtering based on profile
    results = []
    for event in mock_events:
        # Category filter
        if profile.categories:
            category_names = [c.value for c in profile.categories]
            if event.category not in category_names:
                continue

        # Constraints filter
        if profile.constraints:
            if profile.constraints.free_only and event.price and event.price > 0:
                continue
            if (
                profile.constraints.max_distance_miles
                and event.distance_miles
                and event.distance_miles > profile.constraints.max_distance_miles
            ):
                continue

        results.append(event.to_dict())

    return results


@function_tool
def refine_results(
    previous_results: list[dict],
    feedback: list[EventFeedback],
) -> dict:
    """
    Refine search results based on user feedback.

    Analyzes Yes/No/Maybe ratings and reasons to adjust recommendations.
    Returns refined results with an explanation of what changed.

    Args:
        previous_results: Events from the previous search
        feedback: User ratings with optional reasons (too far, too expensive, wrong vibe)

    Returns:
        Dictionary with 'events' (refined list) and 'explanation' (what changed)
    """
    # Analyze feedback patterns
    constraints_learned = []
    preferences_learned = []

    for fb in feedback:
        event = next(
            (e for e in previous_results if e.get("event_id") == fb.event_id), None
        )
        if not event:
            continue

        if fb.rating == Rating.NO and fb.reason:
            reason_lower = fb.reason.lower()
            if "far" in reason_lower or "distance" in reason_lower:
                # User wants closer events
                if event.get("distance_miles"):
                    constraints_learned.append(
                        {
                            "type": "distance",
                            "max": event["distance_miles"] * 0.7,
                            "trigger": event["title"],
                        }
                    )
            if "expensive" in reason_lower or "price" in reason_lower or "cost" in reason_lower:
                # User wants cheaper events
                if event.get("price"):
                    constraints_learned.append(
                        {
                            "type": "price",
                            "max": event["price"] * 0.8,
                            "trigger": event["title"],
                        }
                    )
            if "vibe" in reason_lower or "not my thing" in reason_lower:
                # User doesn't like this category/style
                constraints_learned.append(
                    {
                        "type": "category_exclude",
                        "category": event.get("category"),
                        "trigger": event["title"],
                    }
                )

        elif fb.rating == Rating.YES:
            # User likes this type of event
            preferences_learned.append(
                {
                    "category": event.get("category"),
                    "trigger": event["title"],
                }
            )

    # Build explanation
    explanation_parts = []

    for constraint in constraints_learned:
        if constraint["type"] == "distance":
            explanation_parts.append(
                f"Showing closer events since you said {constraint['trigger']} was too far"
            )
        elif constraint["type"] == "price":
            explanation_parts.append(
                f"Filtering to more affordable options since {constraint['trigger']} was too expensive"
            )
        elif constraint["type"] == "category_exclude":
            explanation_parts.append(
                f"Avoiding similar events to {constraint['trigger']}"
            )

    if preferences_learned:
        liked_categories = list(set(p["category"] for p in preferences_learned if p.get("category")))
        if liked_categories:
            explanation_parts.append(
                f"Prioritizing {', '.join(liked_categories)} events based on your likes"
            )

    # Filter and re-rank results
    refined = []
    for event in previous_results:
        # Check hard constraints
        should_exclude = False
        for constraint in constraints_learned:
            if constraint["type"] == "distance":
                if event.get("distance_miles", 0) > constraint["max"]:
                    should_exclude = True
                    break
            elif constraint["type"] == "price":
                if event.get("price", 0) > constraint["max"]:
                    should_exclude = True
                    break
            elif constraint["type"] == "category_exclude":
                if event.get("category") == constraint["category"]:
                    should_exclude = True
                    break

        if not should_exclude:
            refined.append(event)

    # Sort by preference match (liked categories first)
    liked_categories = [p["category"] for p in preferences_learned]

    def sort_key(event: dict) -> int:
        if event.get("category") in liked_categories:
            return 0
        return 1

    refined.sort(key=sort_key)

    explanation = ". ".join(explanation_parts) if explanation_parts else "Showing your refined results"

    return {
        "events": refined,
        "explanation": explanation,
    }


SEARCH_AGENT_INSTRUCTIONS = """You show search results and refine recommendations based on user feedback.

## Your Role
You're helping the user find the perfect events by showing results and learning their preferences through feedback.

## Flow

1. **Show Results**
   - Use the search_events tool to find 5-10 matching events
   - Present each event clearly with: title, date/time, location, category
   - Include distance and price if available
   - Format results in a scannable way

2. **Collect Feedback**
   - Ask the user to rate events: Yes (interested), No (not interested), Maybe (could work)
   - Encourage them to share reasons: "too far", "too expensive", "wrong vibe", "not my scene"
   - Be conversational: "Any of these catch your eye? Let me know what works and what doesn't"

3. **Refine Results**
   - Use the refine_results tool with their feedback
   - Always explain what changed: "I filtered out the farther venues since you said X was too far"
   - Show the refined results

4. **Iterate**
   - Continue until the user finds events they like or says they're done
   - Offer to adjust search criteria if nothing is working

## Presentation Style

Format events like this:
```
🎯 Columbus AI Meetup: LLM Applications
   📅 Friday, Jan 10 at 6:30 PM
   📍 Improving Columbus, 21 E State St (2.1 mi)
   🏷️ AI/ML • Free
```

## Transparency

Always explain your refinements naturally:
- "I'm showing closer events since you mentioned Rev1 was a bit far"
- "Filtered to free events based on your feedback"
- "Prioritizing AI meetups since you liked the Columbus AI one"

## When to Hand Back

If the user wants to change their search criteria significantly (different dates, location, or categories), acknowledge this and indicate the search should restart with new parameters.
"""

search_agent = Agent(
    name="SearchAgent",
    instructions=SEARCH_AGENT_INSTRUCTIONS,
    model="gpt-4o",
    tools=[search_events, refine_results],
)
