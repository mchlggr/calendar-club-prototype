---
date: 2026-01-09T16:32:01Z
researcher: Claude
git_commit: 57f41c8455cb7ffe52bb756c06d76fbd0a4f3ca6
branch: main
repository: calendar-club-prototype
topic: "Conversational Clarifying Question Workflows with OpenAI"
tags: [research, openai, agents-sdk, structured-outputs, temporal-parsing, conversational-ai]
status: complete
last_updated: 2026-01-09
last_updated_by: Claude
---

# Research: Conversational Clarifying Question Workflows with OpenAI

**Date**: 2026-01-09T16:32:01Z
**Researcher**: Claude
**Git Commit**: 57f41c8455cb7ffe52bb756c06d76fbd0a4f3ca6
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

What's the best way to build a conversational clarifying question workflow with OpenAI's Python SDK for an event discovery app? Is there an agent SDK we can upgrade to? What are the best practices for:
- Phase 1: Clarifying questions (location, date/time, category, constraints) → structured query profile
- Phase 2: Taste calibration with Yes/No/Maybe ratings → refined results with explanations

## Summary

**Recommended Stack**: Use the **OpenAI Agents SDK** (`pip install openai-agents`) with **SQLiteSession** for state management. This provides:

1. **Built-in multi-turn conversation state** via Sessions
2. **Agent handoffs** for transitioning between clarifying → search → refinement phases
3. **Structured outputs** with Pydantic models for type-safe query profiles
4. **Streaming support** for responsive UX
5. **FastAPI integration** patterns ready for production

**Key Insight**: OpenAI's API landscape changed significantly in late 2024. The **Responses API** is the new foundation (replacing Chat Completions for agents), and the **Assistants API is deprecated** (sunset August 2026). The Agents SDK is OpenAI's official framework for building multi-turn conversational agents.

---

## Detailed Findings

### 1. OpenAI Agents SDK - The Recommended Approach

**Installation**:
```bash
uv add openai-agents
# or
pip install openai-agents
```

**Why Use It**:
- Released late 2024 as evolution of OpenAI's "Swarm" project
- Production-ready with built-in tracing, guardrails, and session management
- Python 3.9+ (tested on 3.9-3.14)
- Provider-agnostic (supports 100+ LLMs)

#### Core Architecture for Your Use Case

```python
from agents import Agent, Runner, function_tool
from agents.sessions import SQLiteSession
from pydantic import BaseModel, Field
from typing import List, Union, Literal
from enum import Enum

# ========== DATA MODELS ==========

class EventCategory(str, Enum):
    STARTUP = "startup"
    AI = "ai"
    COMMUNITY = "community"

class TimeOfDay(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"

class DateWindow(BaseModel):
    start: str = Field(description="ISO 8601 datetime string")
    end: str = Field(description="ISO 8601 datetime string")
    original_phrase: str = Field(description="User's original phrase, e.g., 'this weekend'")

class Constraints(BaseModel):
    free_only: bool
    max_distance_miles: Union[int, None]
    time_of_day: Union[TimeOfDay, None]

class SearchProfile(BaseModel):
    location: Union[str, None] = None
    date_window: Union[DateWindow, None] = None
    categories: List[EventCategory] = Field(default_factory=list)
    constraints: Union[Constraints, None] = None

class Rating(str, Enum):
    YES = "yes"
    NO = "no"
    MAYBE = "maybe"

class EventFeedback(BaseModel):
    event_id: str
    rating: Rating
    reason: Union[str, None] = None  # "too far", "too expensive", "wrong vibe"

# ========== TOOLS ==========

@function_tool
def search_events(profile: SearchProfile) -> list[dict]:
    """Search for events matching the profile."""
    # Your search implementation
    return []

@function_tool
def refine_results(
    previous_results: list[dict],
    feedback: list[EventFeedback]
) -> tuple[list[dict], str]:
    """Refine results based on feedback, return (results, explanation)."""
    # Your refinement logic
    explanation = "I prioritized hands-on meetups based on your feedback."
    return [], explanation

# ========== AGENTS ==========

# Phase 1: Clarifying Questions Agent
clarifying_agent = Agent(
    name="ClarifyingAgent",
    instructions="""You help users find events by asking 3-6 clarifying questions.

    Ask about:
    1. Location (default to Columbus, OH if not specified)
    2. Date/time window ("this weekend", "next Thursday", etc.)
    3. Category preferences (startup, AI, community events)
    4. Constraints (free only? max distance? time of day?)

    Be conversational, not form-like. Once you have enough info, output a structured
    SearchProfile and hand off to the search agent.

    For temporal phrases like "this weekend", interpret as:
    - Friday 4pm through Sunday 11:59pm local time
    Always explain your interpretation: "I'm interpreting 'this weekend' as Friday evening through Sunday night."
    """,
    model="gpt-4o",
    output_type=SearchProfile,
    handoffs=["search_agent"]  # Will be connected after creation
)

# Phase 2: Search & Refinement Agent
search_agent = Agent(
    name="SearchAgent",
    instructions="""You show search results and refine based on user feedback.

    Flow:
    1. Use search_events tool to find 5-10 events
    2. Present results clearly with: title, date/time, location, category
    3. Ask user to rate: Yes/No/Maybe (with optional reason: too far, too expensive, wrong vibe)
    4. Use refine_results tool to improve recommendations
    5. Explain what changed: "I prioritized closer events since you said X was too far"

    Continue until user is satisfied or says they're done.
    """,
    model="gpt-4o",
    tools=[search_events, refine_results]
)

# Connect handoffs
clarifying_agent.handoffs = [search_agent]

# ========== FASTAPI INTEGRATION ==========

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticBaseModel
import json

app = FastAPI()

class ChatRequest(PydanticBaseModel):
    message: str
    session_id: str

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def event_generator():
        # SQLite session persists conversation across requests
        session = SQLiteSession(request.session_id, "conversations.db")

        streaming_result = await Runner.run_streamed(
            agent=clarifying_agent,
            input=request.message,
            session=session
        )

        async for event in streaming_result.stream_events():
            if event.type == "raw_response":
                yield f"data: {json.dumps({'type': 'text', 'content': event.delta})}\n\n"
            elif event.type == "handoff":
                yield f"data: {json.dumps({'type': 'phase', 'agent': event.agent_name})}\n\n"
            elif event.type == "tool_call":
                yield f"data: {json.dumps({'type': 'action', 'tool': event.tool_name})}\n\n"

        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear session for 'Reset my tastes' feature"""
    session = SQLiteSession(session_id, "conversations.db")
    await session.clear_session()
    return {"message": "Session cleared"}
```

#### Session Management Options

| Session Type | Best For | Notes |
|--------------|----------|-------|
| `SQLiteSession` | MVP, single-server | In-memory or file-based, simple |
| `SQLAlchemySession` | Production with Postgres/MySQL | Handles connection pooling |
| `RedisSession` | Distributed deployments | Multi-server scenarios |
| `EncryptedSession` | Privacy-sensitive | Wraps any session with encryption + TTL |

**For your MVP with SQLite preference**: Use `SQLiteSession("user_123", "conversations.db")`

---

### 2. Structured Outputs with Pydantic

**Critical Limitation**: OpenAI structured outputs don't support native `datetime` objects. Use `str` with ISO 8601 format.

**Pattern for Incremental Profile Building**:

```python
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Union, List

client = OpenAI()

class PartialSearchProfile(BaseModel):
    """All fields nullable for incremental updates"""
    location: Union[str, None] = None
    date_window: Union[DateWindow, None] = None
    categories: List[EventCategory] = Field(default_factory=list)
    constraints: Union[Constraints, None] = None

def update_profile_from_message(
    current_profile: dict,
    user_message: str,
    conversation_history: list
) -> dict:
    """Extract new profile data from user message"""

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": f"""Extract search preferences from the user message.
                Current profile: {json.dumps(current_profile)}
                Only update fields mentioned by the user. Keep existing values."""
            },
            *conversation_history,
            {"role": "user", "content": user_message}
        ],
        response_format=PartialSearchProfile,
    )

    updates = completion.choices[0].message.parsed.model_dump(exclude_none=True)

    # Merge updates into current profile
    for key, value in updates.items():
        if value is not None and value != []:
            current_profile[key] = value

    return current_profile
```

**Key Rules**:
- Use `Union[Type, None]` for optional fields (not `Optional[Type]`)
- No default values except `Field(default_factory=list)` for lists
- Enums prevent hallucination for category fields
- Always validate ISO 8601 strings post-hoc if needed

---

### 3. Temporal Parsing Strategy

**Primary: `dateparser` library** (most mature, 200+ languages)

```bash
uv add dateparser
```

**Hybrid Implementation**:

```python
import dateparser
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

class TemporalParser:
    def __init__(self, user_timezone: str = 'America/New_York'):
        self.tz = ZoneInfo(user_timezone)
        self.settings = {
            'PREFER_DATES_FROM': 'future',
            'TIMEZONE': user_timezone,
            'RETURN_AS_TIMEZONE_AWARE': True,
        }

        # Custom handlers for range expressions
        self.range_handlers = {
            'this weekend': self._parse_weekend,
            'tomorrow night': self._parse_tomorrow_night,
            'tonight': self._parse_tonight,
        }

    def parse(self, user_input: str) -> dict:
        """Parse temporal expression, return structured result with explanation"""
        user_input_lower = user_input.lower()

        # Try custom range handlers first
        for phrase, handler in self.range_handlers.items():
            if phrase in user_input_lower:
                return handler()

        # Fall back to dateparser
        result = dateparser.parse(user_input, settings=self.settings)

        if result:
            return {
                'success': True,
                'start': result.isoformat(),
                'end': None,
                'explanation': f"Interpreted as {result.strftime('%A, %B %d at %I:%M %p %Z')}",
                'original_phrase': user_input
            }

        # LLM fallback for complex cases
        return self._llm_fallback(user_input)

    def _parse_weekend(self) -> dict:
        """Friday 4pm - Sunday 11:59pm"""
        now = datetime.now(self.tz)
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.hour >= 16:
            days_until_friday = 7

        friday = (now + timedelta(days=days_until_friday)).replace(
            hour=16, minute=0, second=0, microsecond=0
        )
        sunday = friday + timedelta(days=2)
        sunday = sunday.replace(hour=23, minute=59, second=59)

        return {
            'success': True,
            'start': friday.isoformat(),
            'end': sunday.isoformat(),
            'explanation': f"Interpreted 'this weekend' as {friday.strftime('%A %I:%M %p')} through {sunday.strftime('%A %I:%M %p')}",
            'original_phrase': 'this weekend'
        }

    def _parse_tomorrow_night(self) -> dict:
        """Tomorrow 6pm - midnight"""
        now = datetime.now(self.tz)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        midnight = tomorrow.replace(hour=23, minute=59, second=59)

        return {
            'success': True,
            'start': tomorrow.isoformat(),
            'end': midnight.isoformat(),
            'explanation': f"Interpreted 'tomorrow night' as {tomorrow.strftime('%A')} 6:00 PM to midnight",
            'original_phrase': 'tomorrow night'
        }

    def _parse_tonight(self) -> dict:
        """Today 6pm - midnight"""
        now = datetime.now(self.tz)
        start = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now.hour >= 18:
            start = now
        end = now.replace(hour=23, minute=59, second=59)

        return {
            'success': True,
            'start': start.isoformat(),
            'end': end.isoformat(),
            'explanation': f"Interpreted 'tonight' as {start.strftime('%I:%M %p')} to midnight",
            'original_phrase': 'tonight'
        }

    def _llm_fallback(self, user_input: str) -> dict:
        """Use LLM for complex/ambiguous expressions"""
        # Implement LLM call here
        return {
            'success': False,
            'needs_clarification': True,
            'question': f'Could you be more specific about "{user_input}"?'
        }
```

**Always explain interpretations** in the UI:
> "Interpreted 'this weekend' as Friday 4pm through Sunday 11:59pm"

---

### 4. Feedback Loop & Explanation Generation

**Pattern for "Shopping Researcher" Style Calibration**:

```python
class PreferenceLearner:
    def process_feedback(
        self,
        feedbacks: list[EventFeedback],
        events_metadata: dict[str, dict]
    ) -> dict:
        """Learn from Yes/No/Maybe ratings"""

        constraints = []
        preferences = []

        for fb in feedbacks:
            event = events_metadata[fb.event_id]

            if fb.rating == Rating.NO and fb.reason:
                if "too far" in fb.reason.lower():
                    # Set hard constraint based on rejected event
                    max_dist = event.get('distance_km', 10) * 0.7
                    constraints.append({
                        'type': 'distance',
                        'max': max_dist,
                        'trigger_event': event['name']
                    })

                if "too expensive" in fb.reason.lower():
                    max_price = event.get('price', 50) * 0.8
                    constraints.append({
                        'type': 'price',
                        'max': max_price,
                        'trigger_event': event['name']
                    })

            elif fb.rating == Rating.YES:
                # Boost similar attributes
                preferences.append({
                    'vibe': event.get('vibe'),
                    'category': event.get('category'),
                    'trigger_event': event['name']
                })

        return {
            'hard_constraints': constraints,
            'soft_preferences': preferences
        }

    def generate_explanation(self, learned: dict) -> str:
        """Generate natural explanation of refinements"""

        parts = []

        for c in learned['hard_constraints']:
            if c['type'] == 'distance':
                parts.append(
                    f"I'm showing closer events (within {c['max']:.0f}km) "
                    f"since you said {c['trigger_event']} was too far"
                )
            elif c['type'] == 'price':
                parts.append(
                    f"I filtered to events under ${c['max']:.0f} "
                    f"since {c['trigger_event']} was too expensive"
                )

        for p in learned['soft_preferences'][:2]:
            if p.get('vibe'):
                parts.append(
                    f"I prioritized {p['vibe']} events like {p['trigger_event']}"
                )

        if len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return f"{parts[0]}, and {parts[1].lower()}"
        else:
            return f"{', '.join(parts[:-1])}, and {parts[-1].lower()}"
```

**Example Output**:
> "I'm showing closer events since you said Tech Networking Mixer was too far, and I prioritized hands-on workshop events like Python Workshop"

---

### 5. OpenAI API Landscape (2025)

**Key Changes**:

| API | Status | Recommendation |
|-----|--------|----------------|
| **Chat Completions** | Stable | Use for simple, single-turn calls |
| **Responses API** | New (2024) | Use for agents with tools/state |
| **Assistants API** | Deprecated | Migrate to Responses API |
| **Agents SDK** | Recommended | Use for multi-turn workflows |

**Responses API** advantages over Chat Completions:
- Persistent reasoning state across turns (~5% better on benchmarks)
- Built-in tools (web search, file search, code interpreter)
- Automatic state management via Conversations API
- 40-80% better cache utilization

**For your FastAPI backend**: The Agents SDK wraps the Responses API and provides the cleanest abstractions. Use it.

---

## Architecture Recommendation for Calendar Club

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Discovery   │  │ Week View    │  │ Share Link       │   │
│  │ Chat UI     │  │ Calendar     │  │ Generator        │   │
│  └──────┬──────┘  └──────────────┘  └──────────────────┘   │
│         │ SSE Streaming                                      │
└─────────┼───────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              OpenAI Agents SDK                       │    │
│  │  ┌──────────────┐    ┌──────────────┐              │    │
│  │  │ Clarifying   │───▶│ Search &     │              │    │
│  │  │ Agent        │    │ Refinement   │              │    │
│  │  │ (Phase 1)    │    │ Agent        │              │    │
│  │  │              │    │ (Phase 2)    │              │    │
│  │  └──────────────┘    └──────────────┘              │    │
│  │         │                   │                       │    │
│  │         └───────┬───────────┘                       │    │
│  │                 ▼                                   │    │
│  │  ┌──────────────────────────────────────────┐      │    │
│  │  │ SQLiteSession (conversations.db)         │      │    │
│  │  │ - Conversation history                   │      │    │
│  │  │ - Search profiles                        │      │    │
│  │  │ - User preferences (Phase 2)             │      │    │
│  │  └──────────────────────────────────────────┘      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ Temporal Parser │  │ Event Search    │                   │
│  │ (dateparser +   │  │ Service         │                   │
│  │  custom ranges) │  │ (external APIs) │                   │
│  └─────────────────┘  └─────────────────┘                   │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation Checklist

### Phase 1 MVP

- [ ] Install `openai-agents` and `dateparser`
- [ ] Define Pydantic models for SearchProfile
- [ ] Create ClarifyingAgent with system prompt
- [ ] Implement SQLiteSession for conversation state
- [ ] Build FastAPI streaming endpoint
- [ ] Implement TemporalParser with custom handlers
- [ ] Add interpretation explanations to responses
- [ ] Create frontend chat UI with SSE support

### Phase 2 Enhancements

- [ ] Add SearchAgent with tools
- [ ] Implement agent handoffs
- [ ] Create PreferenceLearner for feedback processing
- [ ] Add explanation generation for refinements
- [ ] Persist user preferences to profile
- [ ] Add "Reset my tastes" endpoint
- [ ] Implement "why you're seeing this" transparency

---

## Code References

- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- Sessions Guide: https://openai.github.io/openai-agents-python/sessions/
- Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- dateparser: https://dateparser.readthedocs.io/
- FastAPI Streaming: https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse

---

## Open Questions

1. **Token budget per session**: How many clarifying turns before forcing results?
2. **Fallback for LLM failures**: What's the graceful degradation path?
3. **Multi-metro support (V2+)**: How to handle timezone differences in temporal parsing?
4. **Preference persistence across sessions**: Store in SQLite or separate user profiles table?
