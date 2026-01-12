"""
Orchestrator agent that coordinates clarification, search, and refinement.

The orchestrator is the top-level coordinator for event discovery. It:
1. Gathers user preferences and clarifies when needed
2. Calls search_events when ready to search (ALWAYS searches all sources)
3. Calls refine_results when filtering existing results
4. Calls find_similar when finding events similar to a reference

Tool outputs are automatically preserved in SQLiteSession, so the orchestrator
can reference previous search results in subsequent turns.
"""

import logging
from datetime import datetime, timedelta
from typing import Literal

from agents import Agent, function_tool
from pydantic import BaseModel, Field

from api.models import EventResult, SearchResult
from api.models.search import SearchProfile, TimeWindow
from api.models.orchestrator import OrchestratorResponse
from api.agents.search import (
    search_events as _search_events,
    _deduplicate_events,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Tool Input/Output Models
# ============================================================================


class RefineInput(BaseModel):
    """Input for refine_results tool."""

    filter_type: Literal["free_only", "category", "time", "custom"] = Field(
        description="Type of filter to apply"
    )
    free_only: bool | None = Field(
        default=None, description="If True, filter to only free events"
    )
    categories: list[str] | None = Field(
        default=None, description="Filter to these categories only"
    )
    after_time: str | None = Field(
        default=None, description="Filter to events after this ISO datetime"
    )
    before_time: str | None = Field(
        default=None, description="Filter to events before this ISO datetime"
    )
    custom_criteria: str | None = Field(
        default=None, description="Natural language criteria for custom filtering"
    )


class RefineResult(BaseModel):
    """Result from refine_results tool."""

    events: list[EventResult] = Field(description="Filtered events")
    original_count: int = Field(description="How many events before filtering")
    filtered_count: int = Field(description="How many events after filtering")
    explanation: str = Field(description="What filtering was applied")


class SimilarInput(BaseModel):
    """Input for find_similar tool."""

    reference_event_id: str = Field(
        description="ID of the event to find similar ones to"
    )
    reference_title: str = Field(description="Title of the reference event")
    reference_category: str = Field(description="Category of the reference event")
    reference_url: str | None = Field(
        default=None, description="URL of the reference event (for Exa find_similar)"
    )
    exclude_ids: list[str] = Field(
        default_factory=list, description="Event IDs to exclude (already shown)"
    )
    limit: int = Field(default=10, description="Maximum similar events to return")


class SimilarResult(BaseModel):
    """Result from find_similar tool."""

    events: list[EventResult] = Field(description="Similar events found")
    reference_event_id: str = Field(description="ID of the reference event")
    similarity_basis: str = Field(description="What similarity criteria were used")


# ============================================================================
# Tools
# ============================================================================


@function_tool
async def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile.

    IMPORTANT: This tool ALWAYS searches ALL enabled event sources
    (Eventbrite, Meetup, Exa, Posh, etc.) in parallel. Do not try to select
    specific sources.

    The results are automatically deduplicated by URL and title before returning.

    Args:
        profile: Search criteria including:
            - time_window: Required. Start and end datetime for the search.
            - categories: Optional. Event categories like "ai", "startup", "community"
            - keywords: Optional. Keywords to search for
            - free_only: Optional. If True, only return free events
            - location: Optional. Defaults to Columbus, OH

    Returns:
        SearchResult with:
            - events: List of deduplicated EventResult objects
            - source: Attribution string like "eventbrite+meetup+exa"
            - message: Optional user-facing message
    """
    return await _search_events(profile)


@function_tool
async def refine_results(
    events_to_filter: list[EventResult],
    refinement: RefineInput,
) -> RefineResult:
    """
    Filter events based on criteria.

    The orchestrator should pass the events from the previous search_events
    call. The events are in the conversation history as a tool output.

    Args:
        events_to_filter: Events to filter (from previous search)
        refinement: Filter criteria

    Returns:
        RefineResult with filtered events
    """
    original_count = len(events_to_filter)
    filtered = list(events_to_filter)
    explanations: list[str] = []

    # Apply filters
    if refinement.free_only:
        filtered = [e for e in filtered if e.is_free]
        explanations.append("free events only")

    if refinement.categories:
        cats = set(c.lower() for c in refinement.categories)
        filtered = [e for e in filtered if e.category.lower() in cats]
        explanations.append(f"categories: {', '.join(refinement.categories)}")

    if refinement.after_time:
        filtered = [e for e in filtered if e.date >= refinement.after_time]
        explanations.append(f"after {refinement.after_time}")

    if refinement.before_time:
        filtered = [e for e in filtered if e.date <= refinement.before_time]
        explanations.append(f"before {refinement.before_time}")

    explanation = (
        f"Filtered to {', '.join(explanations)}"
        if explanations
        else "No filters applied"
    )

    return RefineResult(
        events=filtered,
        original_count=original_count,
        filtered_count=len(filtered),
        explanation=explanation,
    )


@function_tool
async def find_similar(input_data: SimilarInput) -> SimilarResult:
    """
    Find events similar to a reference event.

    Use this when the user says something like "show me more like the first one"
    or "find similar events to the AI meetup".

    This performs a new search using the reference event's attributes
    (category, keywords extracted from title) and excludes already-shown events.

    Args:
        input_data: Contains reference event info and exclusion list

    Returns:
        SimilarResult with new similar events
    """
    all_events: list[EventResult] = []

    # Build a search profile based on reference event
    # Use category and extract keywords from title
    keywords = input_data.reference_title.lower().split()[:3]

    # Default to next 30 days
    now = datetime.now()
    profile = SearchProfile(
        time_window=TimeWindow(
            start=now,
            end=now + timedelta(days=30),
        ),
        categories=[input_data.reference_category],
        keywords=keywords,
    )

    # Search all sources
    search_result = await _search_events(profile)
    all_events.extend(search_result.events)

    # Deduplicate
    unique_events = _deduplicate_events(all_events)

    # Exclude already-shown events
    exclude_set = set(input_data.exclude_ids)
    filtered = [e for e in unique_events if e.id not in exclude_set]

    # Limit
    filtered = filtered[: input_data.limit]

    return SimilarResult(
        events=filtered,
        reference_event_id=input_data.reference_event_id,
        similarity_basis=f"category:{input_data.reference_category}, keywords:{keywords}",
    )


# ============================================================================
# Orchestrator Instructions
# ============================================================================

ORCHESTRATOR_INSTRUCTIONS_TEMPLATE = """You are an event discovery orchestrator for Columbus, Ohio.

Your job is to help users find local events by:
1. Gathering their preferences (when, what type, any constraints)
2. Searching for events that match
3. Refining results based on feedback

## CRITICAL RULES

### Always Search All Sources
When you call `search_events`, it automatically queries ALL enabled event sources
(Eventbrite, Meetup, Exa, Posh, etc.) in parallel. You do not select sources.
The results are automatically deduplicated and filtered to the time range before you see them.

### No Fabrication
- NEVER invent event details
- NEVER claim events exist when search returns none
- If search returns no results, say so honestly and suggest broadening criteria

### DO NOT List Events in Your Message
- Events are displayed SEPARATELY as structured output below your message
- Your message should be a brief conversational response (1-2 sentences)
- DO NOT include a numbered list of events in your message text
- Just acknowledge the search and let the UI show the events

## FLOW

### Phase 1: Clarification (if needed)
If the user hasn't provided enough info to search, gather:
- **Time range** (REQUIRED): When are they looking? "this weekend", "tonight", "next week"
- **Interests** (helpful): What type of events? AI, startup, community, nightlife, etc.
- **Constraints** (optional): Free only? Specific area?

Convert relative times to specific dates. For example:
- "this weekend" -> actual dates (e.g., "January 18-19, 2026")
- "tonight" -> today's date with evening hours
- "next week" -> Monday through Sunday dates

Generate 2-4 quick picks to help the user respond faster.

### Phase 2: Search
When you have at least a time range, call `search_events` with a SearchProfile.
The tool returns deduplicated results filtered to your time range.

Your message should be brief like:
- "Here's what I found for this weekend!"
- "Found some great events for you."
- "Here are the upcoming AI meetups."

DO NOT list the events in your message - they appear separately in the UI.

### Phase 3: Refinement
If the user asks to filter results ("only free", "only AI events", "evening only"):
- Call `refine_results` with current events and filter criteria
- Brief message: "Here are the free events." (events shown separately)

If the user asks for similar events ("more like the first one"):
- Call `find_similar` with the reference event's details
- Brief message: "Found some similar events." (events shown separately)

### Handling No Results
If search returns no events:
- Be honest: "I didn't find any events matching those criteria"
- Suggest alternatives: broader time range, different categories, etc.

## RESPONSE FORMAT

Your response should always include:
- message: A brief conversational message (DO NOT list events here - they show separately)
- events: Array of events from search results (empty if no results or still clarifying)
- quick_picks: Suggested quick picks [{label, value}] to help user respond
- placeholder: Placeholder text for the chat input
- phase: Current phase (clarifying, searching, presenting, refining)

## EXAMPLES

User: "What's happening this weekend?"
-> Call search_events with time_window for this weekend.
-> Message: "Here's what I found for this weekend!" (events shown separately)

User: "I want to do something fun"
-> Need more info. Message: "When are you looking? This weekend, tonight, or a specific date?"
   Quick picks: ["This weekend", "Tonight", "Next week"]

User: "Only show me free events"
-> Call refine_results with free_only=True on the previous results.
-> Message: "Here are the free options!" (filtered events shown separately)

User: "Find more events like the AI meetup"
-> Call find_similar with that event's details.
-> Message: "Found some similar events for you!" (events shown separately)
"""


def get_orchestrator_instructions(context: object, agent: object) -> str:
    """Generate orchestrator instructions with current date."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    return f"""Today's date is {today}.

{ORCHESTRATOR_INSTRUCTIONS_TEMPLATE}"""


# ============================================================================
# Orchestrator Agent Definition
# ============================================================================

orchestrator_agent = Agent(
    name="orchestrator",
    instructions=get_orchestrator_instructions,
    model="gpt-4o",
    tools=[search_events, refine_results, find_similar],
    output_type=OrchestratorResponse,
)
