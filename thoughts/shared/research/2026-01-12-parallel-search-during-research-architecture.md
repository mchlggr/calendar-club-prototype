---
date: 2026-01-12T08:27:25Z
researcher: Claude
git_commit: fb3dc9172b4395fc1dac28c2405a6425d4605b16
branch: main
repository: calendar-club-prototype
topic: "Parallel Quick Searches During Background Research - Architecture for Interactive Event Discovery"
tags: [research, codebase, sse, background-tasks, exa, parallel-execution, user-interaction]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Parallel Quick Searches During Background Research

**Date**: 2026-01-12T08:27:25Z
**Researcher**: Claude
**Git Commit**: fb3dc9172b4395fc1dac28c2405a6425d4605b16
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

How can the system show quick sample events to users for preference feedback while longer research operations run in the background? What architectural patterns exist and what would need to change?

## Summary

The codebase has the infrastructure foundations for this pattern but they're not fully connected:

1. **SSE connection management** exists with per-session queues but the queue consumer loop is incomplete
2. **Background task manager** exists using `asyncio.create_task()` for fire-and-forget polling
3. **Exa Research** currently blocks the agent with synchronous polling (up to 120s)
4. **Quick Exa Search** is available but not currently used (commented out registration)

The proposed architecture would:
- Start Exa Research as a background task
- Run quick Exa searches in foreground (return immediately)
- Stream quick results via SSE while research runs
- Collect user feedback on events
- Push research results via SSE when complete

## Current Architecture

### Three Async Patterns in Codebase

| Pattern | Implementation | Use Case |
|---------|----------------|----------|
| **Fire-and-forget** | `BackgroundTaskManager.start_webset_discovery()` | Webset polling |
| **Parallel gather** | `asyncio.gather(*tasks)` in `search.py` | Multi-source search |
| **Synchronous polling** | `research_events_adapter()` | Exa Research (BLOCKS) |

### Current Exa Research Flow (Blocking)

```
api/services/exa_research.py:210-286

User message → Orchestrator → search_events tool
                                    ↓
                            research_events_adapter()
                                    ↓
                            create_research_task()
                                    ↓
                            ┌─────────────────────┐
                            │ Polling loop (BLOCKS)│
                            │ 24 polls × 5s = 120s │
                            │ await asyncio.sleep()│
                            └─────────────────────┘
                                    ↓
                            Return results to agent
                                    ↓
                            Agent responds to user
```

**Problem**: The 120-second polling loop blocks the agent from doing anything else.

### Quick Exa Search (Currently Disabled)

```
api/services/exa_client.py:254-327

client.search(query, num_results=100)
    ↓
run_in_threadpool(SDK.search_and_contents)  # ~2-5 seconds
    ↓
Optional: LLM extraction for structured events
    ↓
Return ExaSearchResult[]
```

**Latency**: ~2-5 seconds for search, +5-10s with extraction

**Status**: Registered but commented out in `api/index.py:52`

### SSE Connection Infrastructure

```
api/services/sse_connections.py

SSEConnectionManager
├── _connections: dict[str, SSEConnection]
│   └── SSEConnection
│       ├── session_id: str
│       ├── queue: asyncio.Queue
│       └── active: bool
│
├── register(session_id) → Create connection with queue
├── unregister(session_id) → Mark inactive, remove
├── push_event(session_id, event) → queue.put(event)
└── has_connection(session_id) → Check if active
```

**Gap**: Events are pushed to queues via `queue.put()` at line 71, but there's no corresponding `queue.get()` loop in the streaming endpoint that would read and yield those events.

### Background Task Manager

```
api/services/background_tasks.py:35-257

BackgroundTaskManager
├── _webset_tasks: dict[str, WebsetTask]
├── _lock: asyncio.Lock
│
├── start_webset_discovery(session_id, profile)
│   ├── create_webset() → Get webset_id
│   ├── asyncio.create_task(_poll_webset)  # Fire-and-forget
│   └── Return immediately with webset_id
│
└── _poll_webset(task_info)  # Runs independently
    ├── Poll every 5s for up to 5 minutes
    ├── Check has_connection() before pushing
    └── sse_manager.push_event("more_events", events)
```

**Key Pattern**: Task runs independently after creation, pushes results when complete.

## Proposed Architecture

### Design Goals

1. **Research runs in background** - Don't block the agent
2. **Quick searches return immediately** - ~2-5 second latency
3. **User sees events while waiting** - Interactive preference gathering
4. **Research results arrive via SSE** - Push notification pattern
5. **Optional: feedback injection** - Preferences influence ongoing research

### Proposed Flow

```
User: "Find me some events this weekend"
    ↓
Orchestrator Agent
    ↓
┌─────────────────────────────────────────────────────────────┐
│ PARALLEL EXECUTION                                           │
│                                                              │
│ 1. start_background_research(profile)                       │
│    └── Returns task_id immediately                          │
│    └── Research polls in background (up to 120s)            │
│                                                              │
│ 2. quick_search(profile)                                    │
│    └── Returns ~5-10 events in 2-5 seconds                  │
│    └── Agent presents these to user immediately             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    ↓
Agent: "Here are some events to start. What do you think?"
    ↓
User: "I like this one, not that one"
    ↓
Agent: "Got it! Looking for more like that..."
    ↓
(Meanwhile, research completes)
    ↓
SSE Event: { type: "research_complete", events: [...], task_id: "..." }
    ↓
Frontend: "Found 15 more events from deep research!"
```

### Required Changes

#### 1. Convert Exa Research to Background Task

**Current** (`api/services/exa_research.py:210-286`):
```python
async def research_events_adapter(profile: Any) -> list[ExaSearchResult]:
    # Creates task and polls synchronously (blocks)
    task_id = await client.create_research_task(query, output_schema)
    for poll_num in range(24):  # BLOCKS FOR UP TO 120s
        await asyncio.sleep(5.0)
        status = await client.get_task_status(task_id)
        if status.status == "completed":
            return status.results
    return []
```

**Proposed**:
```python
async def start_research_task(profile: Any, session_id: str) -> str | None:
    """Start research task, returns immediately with task_id."""
    task_id = await client.create_research_task(query, output_schema)

    # Fire-and-forget polling task
    asyncio.create_task(
        _poll_research_and_push(task_id, session_id)
    )

    return task_id

async def _poll_research_and_push(task_id: str, session_id: str):
    """Background polling that pushes results via SSE."""
    sse_manager = get_sse_manager()

    for _ in range(24):
        await asyncio.sleep(5.0)

        if not sse_manager.has_connection(session_id):
            return  # User disconnected

        status = await client.get_task_status(task_id)
        if status.status == "completed":
            await sse_manager.push_event(session_id, {
                "type": "research_complete",
                "events": [convert_to_frontend_format(e) for e in status.results],
                "task_id": task_id,
            })
            return
```

#### 2. Enable Quick Exa Search Tool

**Add new tool** in `api/agents/orchestrator.py`:
```python
@function_tool
async def quick_search(profile: SearchProfile) -> SearchResult:
    """Quick neural web search (~2-5 seconds).

    Use this for immediate results while research runs in background.
    Returns 5-10 events that match the profile.
    """
    client = get_exa_client()
    results = await client.search(
        query=build_query(profile),
        num_results=10,
        extract_events=True,
    )
    return SearchResult(
        events=[convert_exa_result(r) for r in results],
        source="exa-quick",
    )
```

#### 3. Add Background Research Tool

**Add new tool** in `api/agents/orchestrator.py`:
```python
@function_tool
async def start_research(
    profile: SearchProfile,
    session_id: str
) -> ResearchStarted:
    """Start deep research in background.

    Returns immediately with task_id. Results arrive via SSE
    event 'research_complete' when done (30-120 seconds).

    Use quick_search() for immediate results while this runs.
    """
    task_id = await start_research_task(profile, session_id)
    return ResearchStarted(
        task_id=task_id,
        estimated_time_seconds=60,
        message="Research started. Results will arrive soon.",
    )
```

#### 4. Fix SSE Queue Consumer

**Current gap**: Events pushed to queue but never consumed.

**Add to `stream_chat_response()`** in `api/index.py`:
```python
async def stream_chat_response(...) -> AsyncGenerator[str, None]:
    # ... existing agent execution ...

    # After agent response, keep connection open for background events
    if session_id:
        conn = sse_manager.get_connection(session_id)
        if conn:
            # Consumer loop for background events
            while conn.active:
                try:
                    event = await asyncio.wait_for(
                        conn.queue.get(),
                        timeout=30.0
                    )
                    yield sse_event(event["type"], event)
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
                    continue
```

**Alternative**: Use a separate endpoint for background events:
```python
@app.get("/api/events/stream/{session_id}")
async def background_event_stream(session_id: str):
    """SSE stream for background task results."""
    async def event_generator():
        conn = sse_manager.get_connection(session_id)
        if not conn:
            yield sse_event("error", {"message": "Session not found"})
            return

        while conn.active:
            try:
                event = await asyncio.wait_for(conn.queue.get(), timeout=30.0)
                yield sse_event(event["type"], event)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
```

### Agent Instructions Update

```python
ORCHESTRATOR_INSTRUCTIONS = """
...

## Parallel Search Strategy

For comprehensive event discovery, use BOTH quick search AND background research:

1. Call start_research() to begin deep research (runs in background)
2. IMMEDIATELY call quick_search() to get initial results
3. Present quick results to user while research runs
4. Ask for feedback: "Here are some events to start. Which of these interest you?"
5. Use feedback to inform refinement when research completes
6. When research_complete SSE event arrives, present those results too

Example flow:
- User: "Find me tech events this weekend"
- You: [Call start_research AND quick_search in parallel]
- You: "I'm doing a deep search, but here are some events to start:
       [list quick results]
       Do any of these catch your eye?"
- User: "The AI meetup looks good, not interested in the crypto one"
- You: "Great! I'll focus on AI and skip crypto events..."
- [research_complete event arrives]
- You: "My deep research found 12 more events! Based on your preferences..."
"""
```

## Code References

### SSE Infrastructure
- `api/services/sse_connections.py:16-99` - SSEConnectionManager
- `api/services/sse_connections.py:58-78` - `push_event()` method
- `api/index.py:151-157` - SSE registration in stream

### Background Tasks
- `api/services/background_tasks.py:35-257` - BackgroundTaskManager
- `api/services/background_tasks.py:102-104` - `asyncio.create_task()` pattern
- `api/services/background_tasks.py:172-181` - SSE push on completion

### Exa Research (Current Blocking)
- `api/services/exa_research.py:104-149` - `create_research_task()`
- `api/services/exa_research.py:210-286` - Blocking polling adapter
- `api/services/exa_research.py:255-283` - 24-poll loop

### Quick Exa Search
- `api/services/exa_client.py:254-327` - `search()` method
- `api/services/exa_client.py:542-607` - `search_events_adapter()`
- `api/services/exa_client.py:610-623` - Registration (currently commented out)

### Orchestrator Tools
- `api/agents/orchestrator.py:99-124` - Current `search_events` tool
- `api/agents/orchestrator.py:346-352` - Agent tool list
- `api/agents/orchestrator.py:240-331` - Agent instructions

## Architecture Considerations

### Option A: Unified Stream (Recommended for MVP)

- Single SSE connection handles both agent response AND background events
- Simpler frontend - one stream to manage
- Agent response completes, then connection stays open for background events
- Requires queue consumer in existing stream endpoint

### Option B: Dual Streams

- Original `/api/chat/stream` for agent responses
- New `/api/events/stream/{session_id}` for background events
- Frontend manages two connections per session
- Cleaner separation of concerns
- More complex frontend state management

### Option C: Webhook/Polling Hybrid

- Agent returns immediately with task_id
- Frontend polls `/api/research/{task_id}/status`
- Simple, no SSE complexity
- Higher latency (polling interval)
- More server load

### Feedback Injection Strategies

For injecting user preferences into ongoing research:

1. **Post-Research Refinement** (Simplest)
   - Collect feedback during quick results phase
   - Apply as filter/ranking when research completes
   - No mid-stream injection

2. **Cancel and Restart** (Medium complexity)
   - If strong preferences emerge, cancel current research
   - Start new research with refined query
   - Wastes partial research progress

3. **True Mid-Stream Injection** (Complex)
   - Would require Exa API support for query modification
   - Not currently possible with research.create() API
   - Could simulate with multiple smaller research tasks

## Open Questions

1. **Connection Lifetime**: How long should SSE stay open waiting for background events? Timeout after research expected completion?

2. **Reconnection**: If user refreshes page, how to reconnect to pending research results? Store task_id in session?

3. **Multiple Researches**: What if user asks a new question before research completes? Cancel old? Run in parallel?

4. **Feedback Storage**: Where to store user event preferences for later refinement? Session state? New table?

5. **Event Format**: Should background events use same format as inline events, or differentiate (e.g., `research_events` vs `events`)?

## Related Research

- `thoughts/shared/research/2026-01-12-search-agent-tool-architecture.md` - Current single-tool architecture
