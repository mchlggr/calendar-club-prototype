# Orchestrator Agent Architecture Implementation Plan

## Overview

Replace the current two-phase architecture (ClarifyingAgent → direct function call) with an orchestrator-based architecture that coordinates sub-agents for clarification, search, and refinement. This enables conversational refinement ("show me only free events", "more like the first one") while preserving deduplication and the existing event source infrastructure.

## Current State Analysis

### What Exists
- **ClarifyingAgent** (`api/agents/clarifying.py:177-182`): Gathers preferences, no tools, uses session
- **SearchAgent** (`api/agents/search.py:561-566`): Defined but UNUSED, has `search_events` and `refine_results` tools
- **Direct function call** (`api/index.py:233`): `search_events()` called directly, bypassing SearchAgent
- **Event source registry** (`api/services/base.py`): Adapters for Eventbrite, Meetup, Exa, Posh
- **Unified format** (`api/agents/search.py:34-47`): `EventResult` model with deduplication
- **Session persistence** (`api/services/session.py`): SQLiteSession stores conversation history + tool outputs

### Key Discovery
Tool outputs ARE automatically preserved in SQLiteSession. When `search_events` returns results, they become part of the conversation history the LLM sees in subsequent turns. No new caching infrastructure needed.

## Desired End State

```
User Message
     ↓
┌─────────────────────────────────────────┐
│         ORCHESTRATOR AGENT              │
│   (Coordinator with tools + state)      │
│                                         │
│   Tools:                                │
│   • hand_off_to_clarifier              │
│   • search_events                       │
│   • refine_results                      │
│   • find_similar                        │
└─────────────────────────────────────────┘
     │
     ├──► Clarifier sub-agent (when gathering preferences)
     ├──► search_events tool (when ready to search)
     ├──► refine_results tool (when filtering existing results)
     └──► find_similar tool (when "more like this")

     ↓
Unified EventResult[] (deduplicated)
     ↓
SSE Stream → Frontend
```

### Verification
- [ ] User can have multi-turn conversation to clarify preferences
- [ ] Search queries ALL enabled sources by default
- [ ] User can say "only free events" and get filtered results without re-searching
- [ ] User can say "more like the first one" and get similar events
- [ ] No duplicate events sent to client (server-side dedup)
- [ ] Conversation context preserved across turns via SQLiteSession

## What We're NOT Doing

- Per-source tools (e.g., `search_eventbrite`, `search_meetup`) - single `search_events` queries all
- Client-side deduplication - trust server completely
- Latency optimization (streaming orchestrator reasoning, parallel composition) - revisit later
- New ResultsCache service - SDK session persistence sufficient
- Source selection by orchestrator - always search all sources unless user explicitly narrows

## Implementation Approach

The orchestrator is the top-level coordinator. It uses tools to:
1. Hand off to a clarifying sub-agent when gathering user preferences
2. Call `search_events` tool when ready to search (searches ALL sources)
3. Call `refine_results` tool when filtering existing results
4. Call `find_similar` tool when finding similar events

Tool outputs persist in SQLiteSession automatically, so the orchestrator "remembers" previous search results.

---

## Orchestrator Decision Flow

This diagram shows how the orchestrator decides which tool to call based on user input and conversation state.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR DECISION FLOW                               │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────┐
                              │  User Input  │
                              └──────┬───────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   ORCHESTRATOR receives input  │
                    │   + conversation history       │
                    │   + previous tool outputs      │
                    └────────────────┬───────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │      INTENT CLASSIFICATION     │
                    │      (LLM reasoning)           │
                    └────────────────┬───────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
        ▼                            ▼                            ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│  NEW SEARCH   │          │    REFINE     │          │    SIMILAR    │
│   INTENT?     │          │   INTENT?     │          │    INTENT?    │
└───────┬───────┘          └───────┬───────┘          └───────┬───────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│ Examples:         │    │ Examples:         │    │ Examples:         │
│ • "What's         │    │ • "Only free"     │    │ • "More like      │
│   happening?"     │    │ • "Just AI events"│    │   the first one"  │
│ • "AI events      │    │ • "Evening only"  │    │ • "Similar to     │
│   this weekend"   │    │ • "Under $20"     │    │   the AI meetup"  │
│ • "Show me        │    │ • "Filter to      │    │ • "Find more      │
│   concerts"       │    │   tomorrow"       │    │   like that"      │
└───────┬───────────┘    └───────┬───────────┘    └───────┬───────────┘
        │                        │                        │
        ▼                        ▼                        ▼


═══════════════════════════════════════════════════════════════════════════════
                         NEW SEARCH PATH
═══════════════════════════════════════════════════════════════════════════════

        ┌───────────────────────────────────────────────────────┐
        │              Has enough info to search?               │
        │                                                       │
        │  Required: Time range (when?)                         │
        │  Helpful:  Categories, keywords, constraints          │
        └───────────────────────────┬───────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            ┌───────────────┐              ┌───────────────┐
            │      NO       │              │      YES      │
            └───────┬───────┘              └───────┬───────┘
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐      ┌───────────────────────┐
        │  ASK CLARIFYING Q     │      │  CALL search_events   │
        │                       │      │                       │
        │  Generate:            │      │  Build SearchProfile: │
        │  • Message asking     │      │  • time_window        │
        │    for time range     │      │  • categories         │
        │  • Quick picks        │      │  • keywords           │
        │  • Placeholder text   │      │  • free_only          │
        └───────────┬───────────┘      └───────────┬───────────┘
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐      ┌───────────────────────┐
        │  RESPOND to user      │      │  Tool queries ALL     │
        │  (no tool call)       │      │  sources in parallel: │
        │                       │      │  • Eventbrite         │
        │  Output:              │      │  • Meetup             │
        │  • message            │      │  • Exa                │
        │  • quick_picks        │      │  • Posh               │
        │  • placeholder        │      │  • (any registered)   │
        │  • events: []         │      └───────────┬───────────┘
        └───────────────────────┘                  │
                    │                               ▼
                    │                  ┌───────────────────────┐
                    │                  │  Dedup + format       │
                    │                  │  results              │
                    │                  └───────────┬───────────┘
                    │                               │
                    │                               ▼
                    │                  ┌───────────────────────┐
                    │                  │  RESPOND with events  │
                    │                  │                       │
                    │                  │  Output:              │
                    │                  │  • message            │
                    │                  │  • events: [...]      │
                    │                  │  • quick_picks        │
                    │                  └───────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                         ┌─────────────────┐
                         │  WAIT for next  │
                         │  user input     │◄─────────────────────┐
                         └────────┬────────┘                      │
                                  │                               │
                                  └───────────────────────────────┘
                                          (conversation loop)


═══════════════════════════════════════════════════════════════════════════════
                         REFINE PATH
═══════════════════════════════════════════════════════════════════════════════

        ┌───────────────────────────────────────────────────────┐
        │          Have previous search results?                │
        │          (in conversation history)                    │
        └───────────────────────────┬───────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            ┌───────────────┐              ┌───────────────┐
            │      NO       │              │      YES      │
            └───────┬───────┘              └───────┬───────┘
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐      ┌───────────────────────┐
        │  "I don't have any    │      │  CALL refine_results  │
        │  results to filter.   │      │                       │
        │  Would you like to    │      │  Pass:                │
        │  search first?"       │      │  • events from prev   │
        │                       │      │    search_events call │
        │  (no tool call)       │      │  • refinement criteria│
        └───────────────────────┘      └───────────┬───────────┘
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  Filter in-memory     │
                                       │  (no API calls)       │
                                       │                       │
                                       │  • free_only?         │
                                       │  • categories?        │
                                       │  • time range?        │
                                       └───────────┬───────────┘
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  RESPOND with         │
                                       │  filtered events      │
                                       │                       │
                                       │  Output:              │
                                       │  • message explaining │
                                       │    what was filtered  │
                                       │  • events: [filtered] │
                                       └───────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
                         SIMILAR PATH
═══════════════════════════════════════════════════════════════════════════════

        ┌───────────────────────────────────────────────────────┐
        │       Can identify reference event?                   │
        │       (from previous results or user's description)   │
        └───────────────────────────┬───────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            ┌───────────────┐              ┌───────────────┐
            │      NO       │              │      YES      │
            └───────┬───────┘              └───────┬───────┘
                    │                               │
                    ▼                               ▼
        ┌───────────────────────┐      ┌───────────────────────┐
        │  "Which event would   │      │  CALL find_similar    │
        │  you like to find     │      │                       │
        │  similar ones to?"    │      │  Pass:                │
        │                       │      │  • reference event    │
        │  List previous events │      │    (id, title, cat,   │
        │  as options           │      │    url)               │
        │                       │      │  • exclude_ids (all   │
        │  (no tool call)       │      │    previously shown)  │
        └───────────────────────┘      └───────────┬───────────┘
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  Strategy 1:          │
                                       │  Exa find_similar     │
                                       │  (if URL available)   │
                                       │                       │
                                       │  Strategy 2:          │
                                       │  Category + keyword   │
                                       │  search               │
                                       └───────────┬───────────┘
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  Merge + dedup        │
                                       │  (CRITICAL: exclude   │
                                       │   already-shown IDs)  │
                                       └───────────┬───────────┘
                                                   │
                                                   ▼
                                       ┌───────────────────────┐
                                       │  RESPOND with         │
                                       │  similar events       │
                                       │                       │
                                       │  Output:              │
                                       │  • message            │
                                       │  • events: [new only] │
                                       └───────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
                         DECISION SUMMARY TABLE
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│  User Says                    │ Orchestrator Does          │ Tool Called   │
├─────────────────────────────────────────────────────────────────────────────┤
│ "What's happening?"           │ Ask when                   │ (none)        │
│ "This weekend"                │ Search all sources         │ search_events │
│ "AI events tonight"           │ Search all sources         │ search_events │
│ "Only free ones"              │ Filter previous results    │ refine_results│
│ "Just show evening events"    │ Filter previous results    │ refine_results│
│ "More like the first one"     │ Find similar + dedup       │ find_similar  │
│ "Similar to the AI meetup"    │ Find similar + dedup       │ find_similar  │
│ "Actually, concerts instead"  │ New search (all sources)   │ search_events │
│ "What about next week?"       │ New search (all sources)   │ search_events │
└─────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
                         STATE TRANSITIONS
═══════════════════════════════════════════════════════════════════════════════

                              ┌─────────────┐
                              │   START     │
                              └──────┬──────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │         CLARIFYING             │
                    │   (no results yet)             │
                    └────────────────┬───────────────┘
                                     │
                      User provides enough info
                                     │
                                     ▼
                    ┌────────────────────────────────┐
            ┌──────►│         PRESENTING             │◄──────┐
            │       │   (has search results)         │       │
            │       └────────────────┬───────────────┘       │
            │                        │                       │
            │         ┌──────────────┼──────────────┐        │
            │         │              │              │        │
            │         ▼              ▼              ▼        │
            │   ┌──────────┐  ┌──────────┐  ┌──────────┐     │
            │   │ "filter" │  │ "similar"│  │"new srch"│     │
            │   └────┬─────┘  └────┬─────┘  └────┬─────┘     │
            │        │             │             │           │
            │        ▼             ▼             │           │
            │  ┌──────────┐  ┌──────────┐        │           │
            │  │ REFINING │  │ SIMILAR  │        │           │
            │  └────┬─────┘  └────┬─────┘        │           │
            │       │             │              │           │
            │       └──────┬──────┘              │           │
            │              │                     │           │
            └──────────────┴─────────────────────┴───────────┘
                     (all paths return to PRESENTING)


═══════════════════════════════════════════════════════════════════════════════
                         DEDUP POINTS IN FLOW
═══════════════════════════════════════════════════════════════════════════════

  ┌────────────────────┬─────────────────────────────────────────────────────┐
  │ Operation          │ Deduplication                                       │
  ├────────────────────┼─────────────────────────────────────────────────────┤
  │ search_events      │ YES - after merging all sources                     │
  │ refine_results     │ NO  - filtering already-deduped results             │
  │ find_similar       │ YES - after merging Exa + keyword search            │
  │                    │ + exclude already-shown IDs                         │
  │ New search after   │ YES - fresh dedup (independent of previous)         │
  │ presenting results │                                                     │
  └────────────────────┴─────────────────────────────────────────────────────┘

  Key insight: Dedup happens at tool level, not orchestrator level.
  The orchestrator just passes through whatever the tool returns.
```

---

## Phase 1: Create Orchestrator Agent with Tools

### Overview
Define the orchestrator agent with tools for search, refinement, and clarification handoff. Preserve existing `search_events` logic but wrap it as a tool.

### Changes Required:

#### 1.1 Create Orchestrator Agent Module

**File**: `api/agents/orchestrator.py` (NEW)
**Changes**: New file defining orchestrator agent and tools

```python
"""
Orchestrator agent that coordinates clarification, search, and refinement.

The orchestrator is the top-level coordinator for event discovery. It:
1. Hands off to clarifying logic when gathering user preferences
2. Calls search_events when ready to search (ALWAYS searches all sources)
3. Calls refine_results when filtering existing results
4. Calls find_similar when finding events similar to a reference

Tool outputs are automatically preserved in SQLiteSession, so the orchestrator
can reference previous search results in subsequent turns.
"""

from datetime import datetime
from typing import Literal

from agents import Agent, function_tool
from pydantic import BaseModel, Field

from api.models.search import SearchProfile, TimeWindow
from api.agents.search import (
    search_events as _search_events,
    EventResult,
    SearchResult,
)


# ============================================================================
# Tool Input/Output Models
# ============================================================================

class ClarificationResult(BaseModel):
    """Result from clarification handoff."""

    message: str = Field(description="Message to show the user")
    quick_picks: list[dict] = Field(
        default_factory=list,
        description="Suggested quick picks [{label, value}]"
    )
    placeholder: str | None = Field(
        default=None,
        description="Placeholder text for chat input"
    )
    search_profile: SearchProfile | None = Field(
        default=None,
        description="Built search profile if ready to search"
    )
    ready_to_search: bool = Field(
        default=False,
        description="Whether we have enough info to search"
    )


class RefineInput(BaseModel):
    """Input for refine_results tool."""

    filter_type: Literal["free_only", "category", "time", "custom"] = Field(
        description="Type of filter to apply"
    )
    free_only: bool | None = Field(
        default=None,
        description="If True, filter to only free events"
    )
    categories: list[str] | None = Field(
        default=None,
        description="Filter to these categories only"
    )
    after_time: str | None = Field(
        default=None,
        description="Filter to events after this ISO datetime"
    )
    before_time: str | None = Field(
        default=None,
        description="Filter to events before this ISO datetime"
    )
    custom_criteria: str | None = Field(
        default=None,
        description="Natural language criteria for custom filtering"
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
    reference_title: str = Field(
        description="Title of the reference event"
    )
    reference_category: str = Field(
        description="Category of the reference event"
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Event IDs to exclude (already shown)"
    )
    limit: int = Field(
        default=10,
        description="Maximum similar events to return"
    )


class SimilarResult(BaseModel):
    """Result from find_similar tool."""

    events: list[EventResult] = Field(description="Similar events found")
    reference_event_id: str = Field(description="ID of the reference event")
    similarity_basis: str = Field(
        description="What similarity criteria were used"
    )


# ============================================================================
# Tools
# ============================================================================

@function_tool
async def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile.

    IMPORTANT: This tool ALWAYS searches ALL enabled sources (Eventbrite, Meetup,
    Exa, Posh, etc.) in parallel. Do not try to select specific sources.

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
    current_events: list[EventResult],
    refinement: RefineInput,
) -> RefineResult:
    """
    Filter existing search results without re-querying APIs.

    Use this when the user wants to narrow down results they've already seen,
    such as "only show free events" or "only evening events".

    Args:
        current_events: The events to filter (from previous search)
        refinement: The filter criteria to apply

    Returns:
        RefineResult with filtered events and explanation
    """
    original_count = len(current_events)
    filtered = current_events.copy()
    explanations = []

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

    explanation = f"Filtered to {', '.join(explanations)}" if explanations else "No filters applied"

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
    from api.models.search import SearchProfile, TimeWindow
    from datetime import datetime, timedelta

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
    result = await _search_events(profile)

    # Filter out excluded events
    exclude_set = set(input_data.exclude_ids)
    filtered = [e for e in result.events if e.id not in exclude_set]

    # Limit results
    filtered = filtered[:input_data.limit]

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
The results are automatically deduplicated before you see them.

### No Fabrication
- NEVER invent event details
- NEVER claim events exist when search returns none
- If search returns no results, say so honestly and suggest broadening criteria

### Grounded Responses
- Only present events that came from search results
- Include actual details: title, date/time, location, category
- Say "details not available" for missing fields

## FLOW

### Phase 1: Clarification (if needed)
If the user hasn't provided enough info to search, gather:
- **Time range** (REQUIRED): When are they looking? "this weekend", "tonight", "next week"
- **Interests** (helpful): What type of events? AI, startup, community, nightlife, etc.
- **Constraints** (optional): Free only? Specific area?

Convert relative times to specific dates. For example:
- "this weekend" → actual dates (e.g., "January 18-19, 2026")
- "tonight" → today's date with evening hours
- "next week" → Monday through Sunday dates

Generate 2-4 quick picks to help the user respond faster.

### Phase 2: Search
When you have at least a time range, call `search_events` with a SearchProfile.
The tool returns deduplicated results from all sources.

Present results clearly:
1. **Event Title** - Category
   📅 Date/Time
   📍 Location
   💰 Price (or "Free")
   🔗 [Link](url)

### Phase 3: Refinement
If the user asks to filter results ("only free", "only AI events", "evening only"):
- Call `refine_results` with current events and filter criteria
- Present the filtered results

If the user asks for similar events ("more like the first one"):
- Call `find_similar` with the reference event's details
- Present the new similar events

### Handling No Results
If search returns no events:
- Be honest: "I didn't find any events matching those criteria"
- Suggest alternatives: broader time range, different categories, etc.

## EXAMPLES

User: "What's happening this weekend?"
→ This is enough to search! Call search_events with time_window for this weekend.

User: "I want to do something fun"
→ Need more info. Ask: "When are you looking? This weekend, tonight, or a specific date?"
   Quick picks: ["This weekend", "Tonight", "Next week"]

User: "Only show me free events"
→ Call refine_results with free_only=True on the previous results.

User: "Find more events like the AI meetup"
→ Call find_similar with that event's details.
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
)
```

#### 1.2 Create Output Model for Orchestrator

**File**: `api/models/orchestrator.py` (NEW)
**Changes**: Output model for orchestrator responses

```python
"""Output models for the orchestrator agent."""

from pydantic import BaseModel, Field

from api.agents.search import EventResult


class OrchestratorResponse(BaseModel):
    """Structured response from the orchestrator agent."""

    message: str = Field(
        description="Conversational message to show the user"
    )
    quick_picks: list[dict] = Field(
        default_factory=list,
        description="Suggested quick picks [{label, value}]"
    )
    placeholder: str | None = Field(
        default=None,
        description="Placeholder text for chat input"
    )
    events: list[EventResult] = Field(
        default_factory=list,
        description="Events to display (from search or refinement)"
    )
    phase: str = Field(
        default="clarifying",
        description="Current phase: clarifying, searching, presenting, refining"
    )
```

#### 1.3 Update Exports

**File**: `api/agents/__init__.py`
**Changes**: Export orchestrator agent

```python
from api.agents.clarifying import clarifying_agent
from api.agents.search import search_agent, search_events
from api.agents.orchestrator import orchestrator_agent

__all__ = [
    "clarifying_agent",
    "search_agent",
    "search_events",
    "orchestrator_agent",
]
```

### Success Criteria:

#### Automated Verification:
- [x] Type checking passes: `cd api && python -m mypy agents/orchestrator.py`
- [x] Module imports without error: `python -c "from api.agents.orchestrator import orchestrator_agent"`
- [x] All tools are registered: `python -c "from api.agents.orchestrator import orchestrator_agent; print([t.name for t in orchestrator_agent.tools])"`

#### Manual Verification:
- [ ] Review orchestrator instructions for completeness
- [ ] Verify tool signatures match expected behavior

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation before proceeding to the next phase.

---

## Phase 2: Integrate Orchestrator into API Flow

### Overview
Replace the current two-phase flow (ClarifyingAgent → direct search call) with the orchestrator agent. The orchestrator handles the full conversation loop.

### Changes Required:

#### 2.1 Update Chat Stream Endpoint

**File**: `api/index.py`
**Changes**: Use orchestrator instead of clarifying agent + direct search

Replace the current flow at lines 191-316 with orchestrator-based flow:

```python
# At imports (around line 22)
from api.agents.orchestrator import orchestrator_agent

# In stream_chat_response function (replace lines 191-316)
async def stream_chat_response(
    message: str,
    session: SQLiteSession | None = None,
    session_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat response using orchestrator agent."""
    trace_id = str(uuid.uuid4())[:8]
    logger.info("🚀 [Chat] Start | trace=%s session=%s", trace_id, session_id)

    sse_manager = get_sse_manager()

    try:
        # Register SSE connection for background events
        if session_id:
            connection = await sse_manager.register(session_id)
            logger.debug("📡 [SSE] Registered | session=%s", session_id)

        # Run orchestrator agent
        start_time = time.perf_counter()
        result = await Runner.run(
            orchestrator_agent,
            message,
            session=session,
        )
        duration = time.perf_counter() - start_time
        logger.info(
            "✅ [Orchestrator] Complete | trace=%s duration=%.2fs",
            trace_id,
            duration,
        )

        if result.final_output:
            output = result.final_output

            # Stream message content
            if output.message:
                for i in range(0, len(output.message), 10):
                    chunk = output.message[i:i+10]
                    yield sse_event("content", {"content": chunk})
                    await asyncio.sleep(0.01)

            # Send quick picks if present
            if output.quick_picks:
                yield sse_event("quick_picks", {"quick_picks": output.quick_picks})

            # Send placeholder if present
            if output.placeholder:
                yield sse_event("placeholder", {"placeholder": output.placeholder})

            # Send events if present (from search or refinement)
            if output.events:
                events_data = [
                    {
                        "id": evt.id,
                        "title": evt.title,
                        "startTime": evt.date,
                        "location": evt.location,
                        "categories": [evt.category],
                        "url": evt.url,
                        "source": "orchestrator",
                    }
                    for evt in output.events
                ]
                yield sse_event("events", {"events": events_data, "trace_id": trace_id})

        # Signal completion
        yield sse_event("done", {})

    except Exception as e:
        logger.error(
            "❌ [Chat] Error | trace=%s error=%s",
            trace_id,
            str(e),
            exc_info=True,
        )
        error_msg = _format_user_error(e)
        yield sse_event("error", {"message": error_msg})
        yield sse_event("done", {})

    finally:
        if session_id:
            await sse_manager.unregister(session_id)
            logger.debug("📡 [SSE] Unregistered | session=%s", session_id)
```

#### 2.2 Add Orchestrator Output Type

**File**: `api/agents/orchestrator.py`
**Changes**: Add output_type to orchestrator agent

```python
from api.models.orchestrator import OrchestratorResponse

orchestrator_agent = Agent(
    name="orchestrator",
    instructions=get_orchestrator_instructions,
    model="gpt-4o",
    tools=[search_events, refine_results, find_similar],
    output_type=OrchestratorResponse,  # Add structured output
)
```

### Success Criteria:

#### Automated Verification:
- [x] Server starts without errors: `cd api && uvicorn index:app --reload`
- [x] Type checking passes: `cd api && python -m mypy index.py`
- [x] Basic chat request works: `curl -X POST http://localhost:8000/api/chat/stream -H "Content-Type: application/json" -d '{"message": "hi"}'`

#### Manual Verification:
- [ ] Send "What's happening this weekend?" - should trigger search and return events
- [ ] Send "only free events" after search - should filter without re-searching
- [ ] Conversation context preserved across turns
- [ ] Quick picks appear in UI

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the basic flow works before proceeding.

---

## Phase 3: Enhance Refinement and Similar Events

### Overview
Improve the refinement and find_similar tools to work robustly with the conversation context.

### Changes Required:

#### 3.1 Update refine_results to Access Last Results

**File**: `api/agents/orchestrator.py`
**Changes**: Modify refine_results to work with conversation context

The current design passes `current_events` as a parameter. However, with the SDK's session persistence, the orchestrator can reference previous tool outputs in conversation history.

Update the tool to accept just the refinement criteria, and let the orchestrator pass the events:

```python
@function_tool
async def refine_results(
    events_to_filter: list[dict],  # Orchestrator extracts from context
    refinement: RefineInput,
) -> RefineResult:
    """
    Filter events based on criteria.

    The orchestrator should pass the events from the previous search_events
    call. The events are in the conversation history as a tool output.

    Args:
        events_to_filter: Events to filter (as dicts from previous search)
        refinement: Filter criteria

    Returns:
        RefineResult with filtered events
    """
    # Convert dicts back to EventResult if needed
    from api.agents.search import EventResult

    events = []
    for e in events_to_filter:
        if isinstance(e, dict):
            events.append(EventResult(**e))
        else:
            events.append(e)

    original_count = len(events)
    filtered = events.copy()
    explanations = []

    # Apply filters (same as before)
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

    explanation = f"Filtered to {', '.join(explanations)}" if explanations else "No filters applied"

    return RefineResult(
        events=filtered,
        original_count=original_count,
        filtered_count=len(filtered),
        explanation=explanation,
    )
```

#### 3.2 Enhance find_similar with Exa's Find Similar API

**File**: `api/agents/orchestrator.py`
**Changes**: Use Exa's find_similar if the reference event has a URL

```python
@function_tool
async def find_similar(input_data: SimilarInput) -> SimilarResult:
    """
    Find events similar to a reference event.

    Strategy:
    1. If reference has URL, use Exa's find_similar API for semantic similarity
    2. Also do a category+keyword search
    3. Merge and deduplicate results
    4. Exclude already-shown events
    """
    from api.models.search import SearchProfile, TimeWindow
    from api.services.exa_client import ExaClient
    from api.agents.search import _deduplicate_events, _convert_exa_result
    from datetime import datetime, timedelta
    import os

    all_events = []

    # Strategy 1: Exa find_similar (if URL provided and API key configured)
    if input_data.reference_url and os.getenv("EXA_API_KEY"):
        try:
            exa = ExaClient()
            similar_results = await exa.find_similar(
                url=input_data.reference_url,
                num_results=input_data.limit,
                include_text=True,
            )
            for result in similar_results:
                all_events.append(_convert_exa_result(result))
        except Exception as e:
            logger.warning("Exa find_similar failed: %s", e)

    # Strategy 2: Category + keyword search
    keywords = input_data.reference_title.lower().split()[:3]
    now = datetime.now()
    profile = SearchProfile(
        time_window=TimeWindow(
            start=now,
            end=now + timedelta(days=30),
        ),
        categories=[input_data.reference_category],
        keywords=keywords,
    )

    search_result = await _search_events(profile)
    all_events.extend(search_result.events)

    # Deduplicate
    unique_events = _deduplicate_events(all_events)

    # Exclude already-shown events
    exclude_set = set(input_data.exclude_ids)
    filtered = [e for e in unique_events if e.id not in exclude_set]

    # Limit
    filtered = filtered[:input_data.limit]

    return SimilarResult(
        events=filtered,
        reference_event_id=input_data.reference_event_id,
        similarity_basis=f"category:{input_data.reference_category}, keywords:{keywords}",
    )
```

#### 3.3 Update SimilarInput to Include URL

**File**: `api/agents/orchestrator.py`
**Changes**: Add reference_url field

```python
class SimilarInput(BaseModel):
    """Input for find_similar tool."""

    reference_event_id: str = Field(
        description="ID of the event to find similar ones to"
    )
    reference_title: str = Field(
        description="Title of the reference event"
    )
    reference_category: str = Field(
        description="Category of the reference event"
    )
    reference_url: str | None = Field(
        default=None,
        description="URL of the reference event (for Exa find_similar)"
    )
    exclude_ids: list[str] = Field(
        default_factory=list,
        description="Event IDs to exclude (already shown)"
    )
    limit: int = Field(
        default=10,
        description="Maximum similar events to return"
    )
```

### Success Criteria:

#### Automated Verification:
- [x] Type checking passes: `cd api && python -m mypy agents/orchestrator.py`
- [x] Unit tests pass (if any): `cd api && pytest agents/tests/`

#### Manual Verification:
- [ ] Search for events, then say "only free ones" - filters without re-searching
- [ ] Search, then say "more like the AI meetup" - finds similar events
- [ ] Similar events don't duplicate ones already shown

**Implementation Note**: After completing this phase, pause for manual verification of the refinement flow.

---

## Phase 4: Update Tests and Documentation

### Overview
Add tests for the orchestrator and update documentation.

### Changes Required:

#### 4.1 Add Orchestrator Tests

**File**: `api/agents/tests/test_orchestrator.py` (NEW)
**Changes**: Test orchestrator configuration and tools

```python
"""Tests for orchestrator agent."""

import pytest
from api.agents.orchestrator import (
    orchestrator_agent,
    search_events,
    refine_results,
    find_similar,
    ORCHESTRATOR_INSTRUCTIONS_TEMPLATE,
)


class TestOrchestratorAgent:
    """Test orchestrator agent configuration."""

    def test_agent_has_correct_model(self):
        """Agent should use gpt-4o."""
        assert orchestrator_agent.model == "gpt-4o"

    def test_agent_has_tools(self):
        """Agent should have search, refine, and similar tools."""
        tool_names = [tool.name for tool in orchestrator_agent.tools]
        assert "search_events" in tool_names
        assert "refine_results" in tool_names
        assert "find_similar" in tool_names

    def test_agent_has_output_type(self):
        """Agent should have OrchestratorResponse output type."""
        assert orchestrator_agent.output_type is not None


class TestOrchestratorPrompt:
    """Test orchestrator prompt content."""

    def test_prompt_includes_search_all_sources(self):
        """Prompt should emphasize searching all sources."""
        assert "ALL enabled event sources" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "do not select sources" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE.lower()

    def test_prompt_includes_no_fabrication(self):
        """Prompt should include no fabrication rules."""
        assert "NEVER invent" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE

    def test_prompt_includes_phases(self):
        """Prompt should describe all phases."""
        assert "Clarification" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "Search" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "Refinement" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
```

#### 4.2 Update Research Document

**File**: `thoughts/shared/research/2026-01-11-agentic-flow-search-architecture.md`
**Changes**: Add section documenting the new architecture

Add a new section:

```markdown
## Implementation Status

**Completed**: Orchestrator agent architecture implemented per plan at
`thoughts/shared/plans/2026-01-11-orchestrator-agent-architecture.md`

### New Architecture

- **Orchestrator** (`api/agents/orchestrator.py`): Coordinates full conversation
- **Tools**: `search_events`, `refine_results`, `find_similar`
- **Session persistence**: Tool outputs preserved via SQLiteSession
- **Deduplication**: Server-side, before sending to client
```

### Success Criteria:

#### Automated Verification:
- [x] All tests pass: `cd api && pytest agents/tests/`
- [x] No linting errors: `cd api && ruff check .`

#### Manual Verification:
- [ ] Tests cover key orchestrator behaviors
- [ ] Documentation accurately reflects implementation

---

## Testing Strategy

### Unit Tests:
- Orchestrator agent configuration (model, tools, output_type)
- Prompt content (search all sources, no fabrication, phases)
- Tool input/output model validation
- Refinement filter logic

### Integration Tests:
- End-to-end chat flow with orchestrator
- Search → refinement → similar event sequence
- Session persistence across turns

### Manual Testing Steps:
1. Start conversation: "What's happening this weekend?"
   - Should search and return events
2. Refine: "Only free events"
   - Should filter without re-searching
   - Should show subset of previous results
3. Similar: "More like the first one"
   - Should find similar events
   - Should not duplicate already-shown events
4. New search: "Actually, show me AI events next week"
   - Should do fresh search with new criteria
5. Multi-turn context: Verify conversation history preserved

## Performance Considerations

- **Latency**: Additional LLM round-trips for tool selection (acceptable per requirements)
- **Token usage**: Tool outputs in session history increase context size over time
- **Deduplication**: O(n) per search, negligible for typical result sizes

## Migration Notes

- Existing sessions will continue to work (SQLiteSession format unchanged)
- ClarifyingAgent still exported but no longer used in main flow
- SearchAgent tools merged into orchestrator

## References

- Research: `thoughts/shared/research/2026-01-11-agentic-flow-search-architecture.md`
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- Session persistence: https://openai.github.io/openai-agents-python/sessions/
