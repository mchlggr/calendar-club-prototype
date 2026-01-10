# LLM Loop Productionization Plan

## Overview

This plan hardens the Calendar Club AI chat application from demo-quality to production-quality. The focus is on eliminating hallucination risks, enforcing grounded behavior, validating outputs, and ensuring the LLM loop operates honestly and reliably.

**Scope**: Backend LLM infrastructure only. No new features, no frontend redesign, no architectural changes.

## Current State Analysis

### LLM Loop Architecture

```
User Input (frontend)
    ↓
/api/chat/stream (FastAPI)
    ↓
ClarifyingAgent (gpt-4o)
    ↓ outputs SearchProfile
    ↓ handoff
SearchAgent (gpt-4o)
    ↓ calls tools
search_events() / refine_results()
    ↓
EventbriteClient (or mock fallback)
    ↓
SSE stream → Frontend
```

### Critical Issues Identified

| Issue | File:Line | Severity | Risk |
|-------|-----------|----------|------|
| Silent mock data fallback | `api/agents/search.py:154,174,179` | Critical | Hallucination |
| No grounding rules in SearchAgent prompt | `api/agents/search.py:258-305` | Critical | Hallucination |
| refine_results always returns hardcoded data | `api/agents/search.py:226-255` | Critical | Phantom behavior |
| session_id ignored | `api/index.py:93-96` | High | Broken conversations |
| Raw exceptions sent to client | `api/index.py:122` | Medium | Info leak |
| print() instead of logging | Multiple files | Medium | Lost diagnostics |
| No tool output validation | `api/index.py:112-115` | Medium | Malformed data |
| Frontend generates fake URLs | `frontend/.../DiscoveryChat.tsx:52` | Medium | User confusion |

## Desired End State

After this plan is complete:

1. **No silent hallucinations**: Mock data only available when `DEMO_MODE=true`, with explicit user messaging
2. **Grounded agent behavior**: Prompts explicitly prohibit invention; agents state limitations
3. **Validated outputs**: All tool outputs conform to schemas; malformed data rejected
4. **Stateful conversations**: session_id properly wired for multi-turn context
5. **Structured errors**: User-friendly messages without implementation leaks
6. **Observable system**: Structured logging for all LLM operations
7. **Test coverage**: Prompt rendering, tool I/O, and error path tests

### Verification

```bash
# All tests pass
cd /Users/michaelgeiger/gt/calendarclub/mayor/rig && python -m pytest api/ -v

# Type checking passes
cd /Users/michaelgeiger/gt/calendarclub/mayor/rig && python -m mypy api/

# Linting passes
cd /Users/michaelgeiger/gt/calendarclub/mayor/rig && ruff check api/

# Manual: Chat with DEMO_MODE=false and no EVENTBRITE_API_KEY
# → Should get explicit "no event data available" message, NOT mock events
```

## What We're NOT Doing

- Adding new event source integrations (Meetup, Luma, etc.)
- Building authentication or user accounts
- Redesigning the frontend chat flow
- Adding new features or UX changes
- Refactoring for style preferences
- Database migrations or new persistence layers

---

## Phase 1: Eliminate Silent Mock Data Fallback

### Overview

The most critical issue: `search_events()` silently returns fake events when the real API fails or isn't configured. The LLM then presents these as real, causing system-level hallucination.

### Changes Required

#### 1.1 Add DEMO_MODE Environment Gate

**File**: `api/agents/search.py`
**Changes**: Add explicit demo mode check with user-visible indicator

```python
# At top of file, after imports
import logging

logger = logging.getLogger(__name__)

DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
```

#### 1.2 Modify search_events Tool

**File**: `api/agents/search.py`
**Changes**: Replace silent fallback with explicit behavior

Current (lines 140-179):
```python
@function_tool
def search_events(profile: SearchProfile) -> list[EventResult]:
    if not os.getenv("EVENTBRITE_API_KEY"):
        return _get_mock_events()  # SILENT FALLBACK - BAD
    ...
```

New:
```python
class SearchResult(BaseModel):
    """Result from search_events tool."""
    events: list[EventResult]
    source: str = Field(description="Data source: 'eventbrite', 'demo', or 'unavailable'")
    message: str | None = Field(default=None, description="User-facing message about data source")


@function_tool
def search_events(profile: SearchProfile) -> SearchResult:
    """
    Search for events matching the profile.

    Args:
        profile: SearchProfile with location, date_window, categories, constraints

    Returns:
        SearchResult with events list and source attribution
    """
    # Check demo mode first
    if DEMO_MODE:
        logger.info("DEMO_MODE enabled - returning sample events")
        return SearchResult(
            events=_get_mock_events(),
            source="demo",
            message="Showing sample events (demo mode). These are examples, not real events."
        )

    # Check for API key
    api_key = os.getenv("EVENTBRITE_API_KEY")
    if not api_key:
        logger.warning("EVENTBRITE_API_KEY not configured and DEMO_MODE=false")
        return SearchResult(
            events=[],
            source="unavailable",
            message="Event search is not currently available. Please check back later."
        )

    try:
        # Run async fetch
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
            logger.info(f"Eventbrite returned {len(events)} events")
            return SearchResult(
                events=events,
                source="eventbrite",
                message=None
            )
        else:
            logger.info("Eventbrite returned no events for query")
            return SearchResult(
                events=[],
                source="eventbrite",
                message="No events found matching your criteria. Try broadening your search."
            )

    except Exception as e:
        logger.error(f"Eventbrite API error: {e}", exc_info=True)
        return SearchResult(
            events=[],
            source="unavailable",
            message="Event search encountered an error. Please try again."
        )
```

#### 1.3 Update SearchAgent Prompt for Source Attribution

**File**: `api/agents/search.py`
**Changes**: Add grounding rules to prompt

Replace `SEARCH_AGENT_INSTRUCTIONS` (lines 258-305):

```python
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
```

### Success Criteria

#### Automated Verification:
- [ ] `python -m pytest api/agents/tests/test_search.py -v` passes
- [ ] `ruff check api/agents/search.py` passes
- [ ] `mypy api/agents/search.py` passes

#### Manual Verification:
- [ ] With `DEMO_MODE=false` and no `EVENTBRITE_API_KEY`: Chat returns "not available" message, no mock events
- [ ] With `DEMO_MODE=true`: Chat clearly states "sample events" / "demo mode"
- [ ] With valid `EVENTBRITE_API_KEY`: Chat presents real events without disclaimer

**Implementation Note**: After completing this phase and all automated verification passes, pause for manual confirmation before proceeding.

---

## Phase 2: Fix refine_results Phantom Behavior

### Overview

The `refine_results` tool always returns the same 2 hardcoded events regardless of feedback. This is phantom behavior - the model thinks refinement is happening when it's not.

### Changes Required

#### 2.1 Make refine_results Honest

**File**: `api/agents/search.py`
**Changes**: Either implement real refinement or be explicit about limitations

Option A (Recommended - Minimal change, honest behavior):

```python
class RefinementOutput(BaseModel):
    """Output from refine_results tool."""
    events: list[EventResult]
    explanation: str
    source: str = Field(default="refined", description="Always 'refined' or 'unavailable'")


@function_tool
def refine_results(input_data: RefinementInput) -> RefinementOutput:
    """
    Refine search results based on user feedback.

    NOTE: Current implementation provides suggestions based on feedback patterns,
    but does not re-query the event source. A future version will perform
    actual re-searches with adjusted parameters.

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
            elif "expensive" in reason_lower or "cost" in reason_lower or "price" in reason_lower:
                wants_cheaper = True
            elif "vibe" in reason_lower or "type" in reason_lower or "category" in reason_lower:
                wants_different_type = True
        elif fb.rating.value == "yes":
            liked_ids.append(fb.event_id)

    # Build explanation of what we understood
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

    # HONEST LIMITATION: We don't have real refinement yet
    # Return empty with honest message instead of fake events
    if not DEMO_MODE:
        return RefinementOutput(
            events=[],
            explanation=explanation + " However, I don't have additional events to show right now. Would you like to start a new search with different criteria?",
            source="unavailable"
        )

    # In demo mode, return sample refined events with clear labeling
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
            url=None,  # No fake URL
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
            url=None,  # No fake URL
        ),
    ]

    return RefinementOutput(
        events=demo_events,
        explanation=explanation + " Here are some sample alternatives (demo mode).",
        source="demo"
    )
```

### Success Criteria

#### Automated Verification:
- [ ] `python -m pytest api/agents/tests/test_search.py::test_refine_results -v` passes
- [ ] `ruff check api/agents/search.py` passes

#### Manual Verification:
- [ ] With `DEMO_MODE=false`: Refinement returns honest "no additional events" message
- [ ] With `DEMO_MODE=true`: Refinement returns sample events with clear demo labeling
- [ ] Agent prompt guides model to suggest new search when refinement unavailable

**Implementation Note**: After completing this phase, pause for manual confirmation.

---

## Phase 3: Wire Up Session State

### Overview

The `session_id` from requests is ignored. Conversations are stateless, breaking multi-turn context.

### Changes Required

#### 3.1 Pass session_id to Agent Runner

**File**: `api/index.py`
**Changes**: Use OpenAI Agents SDK session support

```python
# Add import at top
from agents import Runner
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

# Modify chat_stream function (lines 70-132)
@app.post("/api/chat/stream")
async def chat_stream(request: ChatStreamRequest) -> StreamingResponse:
    """
    Stream chat responses using Server-Sent Events.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Check for API key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Service temporarily unavailable'})}\n\n"
                logger.error("OPENAI_API_KEY not configured")
                return

            # Log session for debugging
            logger.info(f"Chat stream started for session: {request.session_id[:8]}...")

            # Run agent with streaming and session context
            streaming_result = Runner.run_streamed(
                clarifying_agent,
                input=request.message,
                context={"session_id": request.session_id},  # Pass session context
            )

            async for event in streaming_result.stream_events():
                if event.type == "raw_response_event":
                    if hasattr(event.data, "delta") and event.data.delta:
                        yield f"data: {json.dumps({'type': 'text', 'content': event.data.delta})}\n\n"
                elif event.type == "agent_updated_stream_event":
                    agent_name = event.new_agent.name if event.new_agent else "unknown"
                    logger.info(f"Agent handoff to: {agent_name}")
                    yield f"data: {json.dumps({'type': 'phase', 'agent': agent_name})}\n\n"
                elif event.type == "run_item_stream_event":
                    if hasattr(event.item, "type"):
                        if event.item.type == "tool_call_item":
                            tool_name = getattr(event.item, "name", "unknown")
                            logger.info(f"Tool call: {tool_name}")
                            yield f"data: {json.dumps({'type': 'action', 'tool': tool_name})}\n\n"
                        elif event.item.type == "tool_call_output_item":
                            output = getattr(event.item, "output", None)
                            if output:
                                # Validate output is JSON-serializable
                                try:
                                    json.dumps(output)  # Validation
                                    yield f"data: {json.dumps({'type': 'events', 'data': output})}\n\n"
                                except (TypeError, ValueError) as e:
                                    logger.warning(f"Tool output not JSON-serializable: {e}")

            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            logger.info(f"Chat stream completed for session: {request.session_id[:8]}...")

        except Exception as e:
            logger.exception(f"Chat stream error: {e}")
            # User-friendly error without implementation details
            yield f"data: {json.dumps({'type': 'error', 'error': 'Something went wrong. Please try again.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

#### 3.2 Add Logging Configuration

**File**: `api/index.py`
**Changes**: Add structured logging setup at module level

```python
# After imports, before app creation
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
```

### Success Criteria

#### Automated Verification:
- [ ] `python -m pytest api/tests/test_index.py -v` passes
- [ ] `ruff check api/index.py` passes

#### Manual Verification:
- [ ] Session ID appears in logs
- [ ] Error messages don't expose internal details
- [ ] Tool outputs are validated before streaming

**Implementation Note**: After completing this phase, pause for manual confirmation.

---

## Phase 4: Harden ClarifyingAgent Prompt

### Overview

The ClarifyingAgent prompt is well-written but lacks explicit grounding rules for edge cases.

### Changes Required

#### 4.1 Add Grounding Rules to ClarifyingAgent

**File**: `api/agents/clarifying.py`
**Changes**: Add explicit constraints

```python
CLARIFYING_AGENT_INSTRUCTIONS = """You help users find local events by asking 3-6 clarifying questions.

## Your Role
You're a friendly local events guide helping someone discover what's happening in their area. Be conversational and warm, not robotic or form-like.

## CRITICAL RULES

1. **Stay On Topic**: Only discuss event discovery. If asked about unrelated topics, politely redirect: "I'm here to help you find local events! What kind of events are you interested in?"

2. **No Fabrication**:
   - NEVER invent event names, venues, or details
   - NEVER claim to know about specific events until search results are returned
   - You gather preferences; the search tool finds actual events

3. **Honest Limitations**:
   - If you don't understand a time expression, ask for clarification
   - If a location is ambiguous, ask which they mean
   - Don't guess - ask

## Information to Gather

1. **Location** - Where are they looking for events?
   - Default to Columbus, OH if not specified
   - Accept neighborhoods, cities, or "near me"

2. **Date/Time Window** - When do they want to go?
   - Accept natural phrases: "this weekend", "tonight", "next Thursday"
   - Always explain your interpretation: "I'm interpreting 'this weekend' as Friday evening through Sunday night"
   - For "this weekend": Friday 4pm through Sunday 11:59pm local time

3. **Category Preferences** - What kind of events interest them?
   - startup/tech events
   - AI/ML meetups
   - community gatherings
   - Ask open-ended first, then clarify if needed

4. **Constraints** - Any limitations?
   - Free events only?
   - Maximum distance willing to travel?
   - Preferred time of day (morning, afternoon, evening, night)?

## Conversation Style

- Ask one or two questions at a time, not all at once
- React naturally to their answers before asking the next question
- It's okay to make reasonable assumptions and confirm them
- If they give vague answers, gently ask for clarification
- Once you have enough information (usually 3-6 exchanges), summarize what you understood

## Output

When you have gathered enough information, output a structured SearchProfile with all the details. This will trigger the search phase.

## Example Flow

User: "What's happening this weekend?"
You: "I'd love to help you find something fun this weekend! I'm interpreting that as Friday evening through Sunday night. Are you in Columbus, or looking somewhere else?"

User: "Yeah Columbus"
You: "Great! What kinds of events interest you? Are you into tech meetups, community events, something more social, or open to anything?"

User: "Tech stuff, maybe AI related"
You: "Nice! AI and tech events it is. Any constraints I should know about - like do you prefer free events, or is there a part of town that works best for you?"

## Handling Edge Cases

- User asks about past events: "I can help you find upcoming events. What dates work for you?"
- User gives contradictory info: "Just to clarify - you mentioned [X] but also [Y]. Which would you prefer?"
- User is vague: "Could you tell me a bit more about what kind of experience you're looking for?"
"""
```

### Success Criteria

#### Automated Verification:
- [ ] `python -m pytest api/agents/tests/test_clarifying.py -v` passes
- [ ] `ruff check api/agents/clarifying.py` passes

#### Manual Verification:
- [ ] Agent stays on topic when asked unrelated questions
- [ ] Agent asks for clarification on ambiguous inputs
- [ ] Agent doesn't invent events during clarification phase

**Implementation Note**: After completing this phase, pause for manual confirmation.

---

## Phase 5: Add Test Coverage

### Overview

Add tests for critical paths: prompt rendering, tool I/O validation, and error handling.

### Changes Required

#### 5.1 Create Agent Tests Directory

```bash
mkdir -p /Users/michaelgeiger/gt/calendarclub/mayor/rig/api/agents/tests
touch /Users/michaelgeiger/gt/calendarclub/mayor/rig/api/agents/tests/__init__.py
```

#### 5.2 Add Search Agent Tests

**File**: `api/agents/tests/test_search.py`

```python
"""Tests for SearchAgent and tools."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from api.agents.search import (
    EventResult,
    RefinementInput,
    RefinementOutput,
    SearchResult,
    _get_mock_events,
    refine_results,
    search_events,
)
from api.models import EventFeedback, Rating, SearchProfile


class TestEventResultModel:
    """Test EventResult Pydantic model validation."""

    def test_valid_event_result(self):
        """Test valid EventResult construction."""
        event = EventResult(
            id="evt-001",
            title="Test Event",
            date="2026-01-10T18:00:00",
            location="Test Venue",
            category="ai",
            description="Test description",
            is_free=True,
            distance_miles=2.5,
        )
        assert event.id == "evt-001"
        assert event.is_free is True

    def test_event_result_with_optional_fields(self):
        """Test EventResult with optional fields."""
        event = EventResult(
            id="evt-002",
            title="Paid Event",
            date="2026-01-10T18:00:00",
            location="Test Venue",
            category="startup",
            description="Test",
            is_free=False,
            price_amount=50,
            distance_miles=3.0,
            url="https://eventbrite.com/e/123",
        )
        assert event.price_amount == 50
        assert event.url == "https://eventbrite.com/e/123"


class TestSearchResult:
    """Test SearchResult model."""

    def test_search_result_with_events(self):
        """Test SearchResult with events."""
        events = _get_mock_events()
        result = SearchResult(
            events=events,
            source="demo",
            message="Demo mode active",
        )
        assert len(result.events) > 0
        assert result.source == "demo"

    def test_search_result_empty(self):
        """Test SearchResult with no events."""
        result = SearchResult(
            events=[],
            source="unavailable",
            message="No events found",
        )
        assert len(result.events) == 0
        assert result.source == "unavailable"


class TestSearchEventsFunction:
    """Test search_events tool function."""

    def test_demo_mode_returns_mock_events(self):
        """With DEMO_MODE=true, should return mock events with demo source."""
        with patch.dict(os.environ, {"DEMO_MODE": "true"}):
            profile = SearchProfile(location="Columbus, OH")
            result = search_events(profile)

            assert result.source == "demo"
            assert len(result.events) > 0
            assert "demo" in result.message.lower() or "sample" in result.message.lower()

    def test_no_api_key_returns_unavailable(self):
        """Without API key and DEMO_MODE=false, should return unavailable."""
        with patch.dict(os.environ, {"DEMO_MODE": "false"}, clear=True):
            # Ensure no EVENTBRITE_API_KEY
            os.environ.pop("EVENTBRITE_API_KEY", None)

            profile = SearchProfile(location="Columbus, OH")
            result = search_events(profile)

            assert result.source == "unavailable"
            assert len(result.events) == 0
            assert result.message is not None


class TestRefineResults:
    """Test refine_results tool function."""

    def test_refine_with_feedback_demo_mode(self):
        """In demo mode, refinement returns sample events."""
        with patch.dict(os.environ, {"DEMO_MODE": "true"}):
            feedback = [
                EventFeedback(event_id="evt-001", rating=Rating.YES),
                EventFeedback(event_id="evt-002", rating=Rating.NO, reason="too far"),
            ]
            input_data = RefinementInput(feedback=feedback)
            result = refine_results(input_data)

            assert result.source == "demo"
            assert "closer" in result.explanation.lower()

    def test_refine_without_demo_mode(self):
        """Without demo mode, refinement is honest about limitations."""
        with patch.dict(os.environ, {"DEMO_MODE": "false"}):
            feedback = [
                EventFeedback(event_id="evt-001", rating=Rating.NO, reason="too expensive"),
            ]
            input_data = RefinementInput(feedback=feedback)
            result = refine_results(input_data)

            assert result.source == "unavailable"
            assert len(result.events) == 0
            # Should suggest alternative action
            assert "search" in result.explanation.lower() or "criteria" in result.explanation.lower()


class TestMockEvents:
    """Test mock event data structure."""

    def test_mock_events_valid(self):
        """Mock events should be valid EventResult instances."""
        events = _get_mock_events()
        assert len(events) >= 3
        for event in events:
            assert isinstance(event, EventResult)
            assert event.id.startswith("evt-")

    def test_mock_events_have_required_fields(self):
        """Mock events should have all required fields."""
        events = _get_mock_events()
        for event in events:
            assert event.title
            assert event.date
            assert event.location
            assert event.category
```

#### 5.3 Add API Endpoint Tests

**File**: `api/tests/test_index.py`

```python
"""Tests for FastAPI endpoints."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.index import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_healthy(self, client):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_returns_ok(self, client):
        """Root endpoint should return ok status."""
        response = client.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestChatStreamEndpoint:
    """Test chat streaming endpoint."""

    def test_missing_openai_key_returns_error(self, client):
        """Without OPENAI_API_KEY, should return error event."""
        with patch.dict("os.environ", {}, clear=True):
            response = client.post(
                "/api/chat/stream",
                json={"session_id": "test-123", "message": "hello"},
            )
            assert response.status_code == 200
            # Should contain error in SSE stream
            content = response.content.decode()
            assert "error" in content.lower()

    def test_valid_request_format(self, client):
        """Request with valid format should be accepted."""
        # This tests request validation, not the full agent flow
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("api.index.Runner") as mock_runner:
                # Mock the streaming result
                mock_runner.run_streamed.return_value.stream_events = AsyncMock(
                    return_value=iter([])
                )

                response = client.post(
                    "/api/chat/stream",
                    json={"session_id": "test-session-123", "message": "What's happening this weekend?"},
                )
                # Should start streaming (200 OK)
                assert response.status_code == 200


class TestCalendarExport:
    """Test calendar export endpoints."""

    def test_export_single_event(self, client):
        """Export single event should return ICS file."""
        response = client.post(
            "/api/calendar/export",
            json={
                "title": "Test Event",
                "start": "2026-01-10T18:00:00",
                "end": "2026-01-10T20:00:00",
                "description": "Test description",
                "location": "Test Venue",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/calendar"
        assert "BEGIN:VCALENDAR" in response.content.decode()

    def test_export_multiple_events(self, client):
        """Export multiple events should return combined ICS file."""
        response = client.post(
            "/api/calendar/export-multiple",
            json={
                "events": [
                    {
                        "title": "Event 1",
                        "start": "2026-01-10T18:00:00",
                    },
                    {
                        "title": "Event 2",
                        "start": "2026-01-11T18:00:00",
                    },
                ]
            },
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert content.count("BEGIN:VEVENT") == 2

    def test_export_empty_events_fails(self, client):
        """Export with no events should return 400."""
        response = client.post(
            "/api/calendar/export-multiple",
            json={"events": []},
        )
        assert response.status_code == 400
```

#### 5.4 Add Prompt Rendering Tests

**File**: `api/agents/tests/test_prompts.py`

```python
"""Tests for agent prompt integrity."""

import pytest

from api.agents.clarifying import CLARIFYING_AGENT_INSTRUCTIONS, clarifying_agent
from api.agents.search import SEARCH_AGENT_INSTRUCTIONS, search_agent


class TestClarifyingAgentPrompt:
    """Test ClarifyingAgent prompt content."""

    def test_prompt_includes_grounding_rules(self):
        """Prompt should include grounding rules."""
        assert "CRITICAL RULES" in CLARIFYING_AGENT_INSTRUCTIONS
        assert "No Fabrication" in CLARIFYING_AGENT_INSTRUCTIONS or "NEVER invent" in CLARIFYING_AGENT_INSTRUCTIONS

    def test_prompt_includes_location_default(self):
        """Prompt should specify default location."""
        assert "Columbus" in CLARIFYING_AGENT_INSTRUCTIONS

    def test_prompt_includes_temporal_interpretation(self):
        """Prompt should guide temporal interpretation."""
        assert "this weekend" in CLARIFYING_AGENT_INSTRUCTIONS
        assert "Friday" in CLARIFYING_AGENT_INSTRUCTIONS

    def test_agent_has_correct_model(self):
        """Agent should use gpt-4o."""
        assert clarifying_agent.model == "gpt-4o"

    def test_agent_has_output_type(self):
        """Agent should have SearchProfile output type."""
        assert clarifying_agent.output_type is not None


class TestSearchAgentPrompt:
    """Test SearchAgent prompt content."""

    def test_prompt_includes_source_attribution(self):
        """Prompt should require source attribution."""
        assert "source" in SEARCH_AGENT_INSTRUCTIONS.lower()
        assert "demo" in SEARCH_AGENT_INSTRUCTIONS.lower()

    def test_prompt_includes_zero_result_handling(self):
        """Prompt should handle zero results."""
        assert "empty" in SEARCH_AGENT_INSTRUCTIONS.lower() or "no events" in SEARCH_AGENT_INSTRUCTIONS.lower()

    def test_prompt_prohibits_fabrication(self):
        """Prompt should prohibit making up events."""
        assert "NEVER" in SEARCH_AGENT_INSTRUCTIONS or "never" in SEARCH_AGENT_INSTRUCTIONS.lower()
        assert "fabricat" in SEARCH_AGENT_INSTRUCTIONS.lower() or "invent" in SEARCH_AGENT_INSTRUCTIONS.lower()

    def test_agent_has_tools(self):
        """Agent should have search and refine tools."""
        tool_names = [t.name for t in search_agent.tools]
        assert "search_events" in tool_names
        assert "refine_results" in tool_names

    def test_agent_has_correct_model(self):
        """Agent should use gpt-4o."""
        assert search_agent.model == "gpt-4o"
```

### Success Criteria

#### Automated Verification:
- [ ] `python -m pytest api/ -v` - All tests pass
- [ ] `python -m pytest api/ --cov=api --cov-report=term-missing` - Coverage report generated

#### Manual Verification:
- [ ] Test output is clear and informative
- [ ] No flaky tests

**Implementation Note**: After completing this phase, pause for manual confirmation.

---

## Phase 6: Environment and Configuration Cleanup

### Overview

Clean up environment configuration and add proper .env.example documentation.

### Changes Required

#### 6.1 Create Comprehensive .env.example

**File**: `api/.env.example` (create or update)

```bash
# Calendar Club API Configuration
# Copy this file to .env and fill in your values

# =============================================================================
# REQUIRED
# =============================================================================

# OpenAI API Key - Required for LLM functionality
# Get yours at: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...

# =============================================================================
# EVENT SOURCES (at least one required for real data)
# =============================================================================

# Eventbrite API Key - For real event discovery
# Get yours at: https://www.eventbrite.com/platform/api-keys
EVENTBRITE_API_KEY=

# =============================================================================
# OPTIONAL
# =============================================================================

# Demo Mode - Set to "true" to show sample events without real API
# Useful for development and demos. Default: false
DEMO_MODE=false

# CORS Origins - Comma-separated list of allowed origins
# Default: http://localhost:3000,http://localhost:3001
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Log Level - DEBUG, INFO, WARNING, ERROR
# Default: INFO
LOG_LEVEL=INFO

# =============================================================================
# OBSERVABILITY (optional)
# =============================================================================

# HyperDX API Key - For telemetry and monitoring
HYPERDX_API_KEY=
```

#### 6.2 Add Logging Configuration Module

**File**: `api/config.py` (new file)

```python
"""Configuration management for Calendar Club API."""

import logging
import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Required
    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Event sources
    eventbrite_api_key: str = Field(default="", description="Eventbrite API key")

    # Feature flags
    demo_mode: bool = Field(default=False, description="Enable demo mode with sample events")

    # Server config
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        description="Comma-separated CORS origins",
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # Observability
    hyperdx_api_key: str = Field(default="", description="HyperDX API key")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def has_event_source(self) -> bool:
        """Check if any event source is configured."""
        return bool(self.eventbrite_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def configure_logging(settings: Settings | None = None) -> None:
    """Configure application logging."""
    if settings is None:
        settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
```

#### 6.3 Update index.py to Use Config

**File**: `api/index.py`
**Changes**: Use centralized config

```python
# Replace manual os.getenv calls with:
from api.config import configure_logging, get_settings

# At module initialization
configure_logging()
settings = get_settings()

# Then use settings.cors_origins_list, settings.demo_mode, etc.
```

### Success Criteria

#### Automated Verification:
- [ ] `python -c "from api.config import get_settings; print(get_settings())"` - Config loads
- [ ] `ruff check api/config.py` passes

#### Manual Verification:
- [ ] .env.example is clear and comprehensive
- [ ] Missing required vars produce clear error messages

**Implementation Note**: After completing this phase, pause for manual confirmation.

---

## Testing Strategy

### Unit Tests

Location: `api/agents/tests/`, `api/tests/`

| Test File | Coverage |
|-----------|----------|
| `test_search.py` | Search tool, mock data, refinement |
| `test_index.py` | API endpoints, error handling |
| `test_prompts.py` | Prompt content validation |
| `test_temporal_parser.py` | Temporal parsing (existing) |

### Integration Tests

```bash
# Run all tests
cd /Users/michaelgeiger/gt/calendarclub/mayor/rig && python -m pytest api/ -v

# Run with coverage
cd /Users/michaelgeiger/gt/calendarclub/mayor/rig && python -m pytest api/ --cov=api --cov-report=html
```

### Manual Testing Checklist

1. **Demo Mode Flow**
   - Set `DEMO_MODE=true`, remove `EVENTBRITE_API_KEY`
   - Chat should clearly indicate sample/demo events
   - No fake URLs should appear

2. **Production Mode Flow**
   - Set `DEMO_MODE=false`, no `EVENTBRITE_API_KEY`
   - Chat should say "event search not available"
   - No mock events should appear

3. **Real API Flow**
   - Set `DEMO_MODE=false`, valid `EVENTBRITE_API_KEY`
   - Chat should show real Eventbrite events
   - Handle zero results gracefully

4. **Error Handling**
   - Remove `OPENAI_API_KEY`
   - Chat should show user-friendly error
   - No stack traces in response

---

## Performance Considerations

- **No new dependencies**: Uses existing OpenAI Agents SDK, Pydantic
- **No database changes**: Session handling uses existing SQLiteSession
- **Minimal prompt changes**: Only adds grounding rules, doesn't restructure
- **Backward compatible**: API contracts unchanged

---

## Migration Notes

### Environment Variables

New variables to add:
- `DEMO_MODE` (optional, default: false)
- `LOG_LEVEL` (optional, default: INFO)

### Breaking Changes

- `search_events` tool now returns `SearchResult` instead of `list[EventResult]`
- `refine_results` tool now returns `RefinementOutput` with `source` field
- Agent must handle new response format

Frontend compatibility: The SSE stream format is unchanged. Frontend receives same event types.

---

## References

- Production readiness research: `throughts/research/2026-01-09-production-readiness-gaps.md`
- Existing implementation plan: `throughts/plans/2026-01-09-production-readiness-implementation.md`
- Tech stack: `TECHSTACK.md`

---

## Repo-Specific Best Practices

### Prompt Conventions

1. All agent prompts must include a `## CRITICAL RULES` or `## CRITICAL GROUNDING RULES` section
2. Rules must explicitly prohibit fabrication: "NEVER invent", "NEVER make up"
3. Source attribution must be mandatory for any data-returning operation
4. Zero-result handling must be explicit: what to say, what NOT to do

### Tool Usage Rules

1. All tools returning data must include a `source` field: `"eventbrite"`, `"demo"`, `"unavailable"`
2. Tools must include a `message` field for user-facing context when appropriate
3. Silent fallbacks are prohibited - every data path must be explicit
4. Tool outputs must be JSON-serializable and validated before streaming

### Grounding Policy

1. Retrieved data is the ONLY source of truth for event information
2. Zero results = honest "no results" message, never fabricated alternatives
3. Demo/sample data must be explicitly labeled in both data AND user messaging
4. Unknown inputs trigger clarification requests, not assumptions

### Extension Guidelines

When adding new event sources:
1. Follow `EventbriteClient` pattern in `api/services/`
2. Add source identifier to `SearchResult.source` enum
3. Update `search_events` to try new source
4. Add tests for new source in `api/agents/tests/test_search.py`

When modifying prompts:
1. Run `python -m pytest api/agents/tests/test_prompts.py` to verify rules intact
2. Never remove grounding rules without explicit approval
3. Add new edge case handling to `## Handling Edge Cases` section
