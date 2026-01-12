# Event Flow Logging Implementation Plan

## Overview

Add comprehensive event flow logging to diagnose where events are lost, filtered, or transformed incorrectly as they flow from backend integrations through SSE streaming to frontend display. Currently, only aggregate counts are logged, making it impossible to track individual events through the system.

## Current State Analysis

### What IS Logged (Counts Only)
- Per-source event counts after fetch (`api/agents/search.py:300-304`)
- Deduplication stats: before/after/removed counts (`api/agents/search.py:321-326`)
- SSE streaming count (`api/index.py:228-232`)

### What is NOT Logged
- **Individual event titles/IDs** at any point in the pipeline
- **Which events were removed** during deduplication
- **Why events were removed** (URL match vs title match)
- **Frontend event reception** (only 4 console statements exist, all for errors)
- **JSON parse failures** in SSE stream (silently ignored)
- **Unhandled event types** (`more_events` from background tasks)

### Key Loss Points Identified
1. Conversion errors - events silently dropped with warning log (`api/agents/search.py:214-219`)
2. Deduplication - no visibility into which events removed (`api/agents/search.py:174-191`)
3. 15 event limit - events beyond limit silently truncated (`api/agents/search.py:330`)
4. SSE parse errors - frontend silently skips malformed JSON (`api.ts:174-178`)
5. Missing handler - `more_events` type not handled (`DiscoveryChat.tsx:112-176`)

## Desired End State

After this implementation:
1. **Backend DEBUG logs** show each event title/ID at key transformation points
2. **Deduplication logs** identify which specific events were removed and why
3. **Frontend debug mode** can be enabled to log all SSE events received
4. **`more_events` handler** displays background websets results
5. **Trace IDs** correlate events from backend to frontend

### Verification
- Set `LOG_LEVEL=DEBUG` and observe individual event titles in backend logs
- Enable frontend debug mode via `localStorage.setItem('DEBUG_EVENTS', 'true')` and verify console logs
- Trigger a search and confirm `more_events` results appear (may take 15-30s)
- Verify trace ID appears in both backend and frontend logs for the same search

## What We're NOT Doing

- **Changing logging levels** - All new logging is DEBUG level, won't affect production
- **Fixing the 500ms timeout window** - Background event delivery timing is a separate issue
- **Adding persistent logging storage** - This is for real-time debugging only
- **Changing deduplication algorithm** - Only adding visibility, not changing behavior
- **Adding frontend analytics** - PostHog/HyperDX already track events; this is for debugging

## Implementation Approach

Follow the existing emoji logging convention (`api/README.md:84-101`):
- `📋` for individual event logging (new emoji for event details)
- Maintain structured format: `"emoji [Component] Description | key=value"`
- Frontend uses conditional logging gated by localStorage flag
- All logging is DEBUG level to avoid production noise

---

## Phase 1: Backend Individual Event Logging

### Overview
Add DEBUG-level logging of individual event titles and IDs at key points in the backend pipeline, maintaining the existing emoji/structured logging convention.

### Changes Required:

#### 1.1 Add Event Detail Logging After Source Fetch

**File**: `api/agents/search.py`
**Location**: After line 298 (inside the conversion loop)

Add logging of each event title after successful conversion:

```python
# After line 298: all_events.extend(converted)
# Add individual event logging
if logger.isEnabledFor(logging.DEBUG):
    for event in converted:
        logger.debug(
            "📋 [Search] Event from source | source=%s id=%s title=%s",
            source_name,
            event.id[:20] if event.id else "none",
            event.title[:50] if event.title else "untitled",
        )
```

#### 1.2 Add Deduplication Detail Logging

**File**: `api/agents/search.py`
**Location**: Replace lines 174-197 (`_deduplicate_events` function)

```python
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
```

#### 1.3 Log Events Being Streamed to SSE

**File**: `api/index.py`
**Location**: After line 226 (where events_data is created)

```python
# After events_data = [...] at line 226
# Add individual event logging before streaming
if logger.isEnabledFor(logging.DEBUG):
    for ev in events_data:
        logger.debug(
            "📋 [SSE] Streaming event | session=%s id=%s title=%s",
            session_id or "None",
            ev.get("id", "none")[:20],
            ev.get("title", "untitled")[:50],
        )
```

#### 1.4 Log Truncation When Limit Applied

**File**: `api/agents/search.py`
**Location**: After line 330 (where limit is applied)

```python
# After: unique_events = unique_events[:15]
if len(unique_events) < len(sorted_events):
    truncated_count = len(sorted_events) - len(unique_events)
    logger.debug(
        "📋 [Search] Truncated results | kept=%d removed=%d",
        len(unique_events),
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
```

### Success Criteria:

#### Automated Verification:
- [x] Type checking passes: `make -C api typecheck` (or `mypy api/`)
- [x] Linting passes: `make -C api lint` (or `ruff check api/`)
- [x] Unit tests pass: `make -C api test`
- [ ] Start server with `LOG_LEVEL=DEBUG uv run uvicorn api.index:app --reload`

#### Manual Verification:
- [ ] Trigger a search query and verify individual event titles appear in DEBUG logs
- [ ] Verify deduplication logs show which events were removed and why (URL vs title)
- [ ] Verify truncation logs show which events were cut when >15 results
- [ ] Confirm logs follow emoji convention: `📋 [Component] Description | key=value`

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the logging output is useful before proceeding to the next phase.

---

## Phase 2: Frontend Debug Logging

### Overview
Add conditional console logging to the frontend that can be enabled via localStorage flag for debugging SSE event flow.

### Changes Required:

#### 2.1 Create Debug Logger Utility

**File**: `frontend/src/lib/debug.ts` (new file)

```typescript
/**
 * Debug logging utility for event flow tracing.
 * Enable with: localStorage.setItem('DEBUG_EVENTS', 'true')
 * Disable with: localStorage.removeItem('DEBUG_EVENTS')
 */

const isDebugEnabled = (): boolean => {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("DEBUG_EVENTS") === "true";
};

export const debugLog = (
  component: string,
  message: string,
  data?: Record<string, unknown>
): void => {
  if (!isDebugEnabled()) return;

  const timestamp = new Date().toISOString().slice(11, 23); // HH:mm:ss.SSS
  const dataStr = data ? ` | ${Object.entries(data).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ")}` : "";
  console.debug(`[${timestamp}] [${component}] ${message}${dataStr}`);
};

export const debugWarn = (
  component: string,
  message: string,
  data?: Record<string, unknown>
): void => {
  if (!isDebugEnabled()) return;

  const timestamp = new Date().toISOString().slice(11, 23);
  const dataStr = data ? ` | ${Object.entries(data).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ")}` : "";
  console.warn(`[${timestamp}] [${component}] ${message}${dataStr}`);
};
```

#### 2.2 Add SSE Stream Logging

**File**: `frontend/src/lib/api.ts`
**Location**: Around line 171 (inside the SSE parsing loop)

Add import at top:
```typescript
import { debugLog, debugWarn } from "./debug";
```

Add logging after successful parse (around line 172):
```typescript
try {
    const data = JSON.parse(line.slice(6)) as ChatStreamEvent;
    debugLog("SSE", "Event received", { type: data.type, hasEvents: !!data.events, eventCount: data.events?.length });
    onChunk(data);
} catch (e) {
    if (e instanceof SyntaxError) {
        debugWarn("SSE", "JSON parse error (skipped)", { line: line.slice(0, 100) });
        continue;
    }
    throw e;
}
```

#### 2.3 Add Event Mapping Logging

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx`
**Location**: In the `type: "events"` handler (around line 130-138)

Add import at top:
```typescript
import { debugLog } from "@/lib/debug";
```

Add logging in the events handler:
```typescript
} else if (event.type === "events" && event.events) {
    debugLog("Events", "Received from backend", { count: event.events.length });

    // Log individual events before mapping
    event.events.forEach((ev, i) => {
        debugLog("Events", `Raw event ${i}`, { id: ev.id, title: ev.title?.slice(0, 50), startTime: ev.startTime });
    });

    const mappedEvents = event.events.map(mapApiEventToCalendarEvent);

    debugLog("Events", "Mapped to calendar format", { count: mappedEvents.length });

    setPendingResults(mappedEvents);
    onResultsReady(mappedEvents);
    // ... rest of handler
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `make -C frontend typecheck` (or `cd frontend && npm run typecheck`)
- [x] Linting passes: `make -C frontend lint`
- [x] Build succeeds: `make -C frontend build` (or `cd frontend && npm run build`)

#### Manual Verification:
- [ ] Open browser console, run `localStorage.setItem('DEBUG_EVENTS', 'true')`
- [ ] Refresh page and trigger a search
- [ ] Verify console shows `[SSE] Event received` logs with event types
- [ ] Verify `[Events] Received from backend` shows event count
- [ ] Verify individual event details logged before mapping
- [ ] Run `localStorage.removeItem('DEBUG_EVENTS')` and confirm logs stop

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the frontend debug logging is helpful before proceeding to the next phase.

---

## Phase 3: Fix Missing `more_events` Handler

### Overview
The backend sends `more_events` from background websets discovery, but the frontend has no handler for this event type. Events from background discovery are silently lost.

### Changes Required:

#### 3.1 Add Type Definition for `more_events`

**File**: `frontend/src/lib/api.ts`
**Location**: Update `ChatStreamEvent` interface (around line 46-57)

```typescript
export interface ChatStreamEvent {
    type:
        | "content"
        | "done"
        | "error"
        | "events"
        | "more_events"      // Add this
        | "background_search" // Add this
        | "action"
        | "phase"
        | "quick_picks"
        | "placeholder"
        | "ready_to_search"
        | "searching";
    content?: string;
    message?: string;
    error?: string;
    quick_picks?: QuickPickOption[];
    placeholder?: string;
    events?: DiscoveryEventWire[];
    phase?: string;
    action?: string;
    source?: string;  // Add for more_events source tracking
}
```

#### 3.2 Add Handler for `more_events`

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx`
**Location**: In `handleChunk` function, after the `events` handler (around line 138)

```typescript
} else if (event.type === "more_events" && event.events) {
    debugLog("Events", "Background discovery results", {
        count: event.events.length,
        source: event.source
    });

    const mappedEvents = event.events.map(mapApiEventToCalendarEvent);

    // Merge with existing results, avoiding duplicates
    setPendingResults((prev) => {
        const existingIds = new Set(prev.map((e) => e.id));
        const newEvents = mappedEvents.filter((e) => !existingIds.has(e.id));
        debugLog("Events", "Merged background results", {
            existing: prev.length,
            new: newEvents.length,
            total: prev.length + newEvents.length
        });
        return [...prev, ...newEvents];
    });

    // Notify parent of updated results
    onResultsReady(mappedEvents);

    trackEventsDiscovered({
        count: mappedEvents.length,
        categories: mappedEvents.map((e) => e.category),
        source: event.source || "background",
    });
} else if (event.type === "background_search") {
    // Background search started notification - could show subtle indicator
    debugLog("Events", "Background search started", { message: event.message });
```

### Success Criteria:

#### Automated Verification:
- [x] TypeScript compiles: `make -C frontend typecheck`
- [x] Linting passes: `make -C frontend lint`
- [x] Build succeeds: `make -C frontend build`

#### Manual Verification:
- [ ] Trigger a search and wait 15-30 seconds for background results
- [ ] With debug enabled, verify `[Events] Background discovery results` appears in console
- [ ] Verify new events are merged with existing results (not replacing)
- [ ] Verify PostHog receives `events_discovered` event with source="background"

**Implementation Note**: Background websets may take 15-30 seconds to complete. The current 500ms connection timeout may still cause these events to be lost - that's a separate architectural issue. This phase ensures the frontend CAN handle these events when they arrive.

---

## Phase 4: Add Trace ID for Correlation

### Overview
Add a trace ID that flows from backend to frontend, allowing correlation of events across the system boundary.

### Changes Required:

#### 4.1 Generate Trace ID in Backend

**File**: `api/index.py`
**Location**: At the start of `stream_chat_response` function (around line 130)

Add import at top:
```python
import uuid
```

Add trace ID generation:
```python
async def stream_chat_response(
    message: str,
    session: SessionHistory,
    session_id: str | None = None,
) -> AsyncIterator[str]:
    """Stream chat response using SSE."""
    # Generate trace ID for this request
    trace_id = str(uuid.uuid4())[:8]  # Short trace ID for readability

    logger.debug("🔍 [Chat] Request started | trace=%s session=%s", trace_id, session_id or "None")
```

#### 4.2 Include Trace ID in Event Logs

Update all DEBUG logs in `stream_chat_response` to include the trace ID:

```python
# Example: Update SSE streaming log (around line 228)
logger.debug(
    "📤 [SSE] Streaming events | trace=%s session=%s count=%d",
    trace_id,
    session_id or "None",
    len(events_data),
)
```

#### 4.3 Send Trace ID to Frontend

**File**: `api/index.py`
**Location**: Add trace ID to the `events` SSE payload (around line 227)

```python
yield sse_event("events", {"events": events_data, "trace_id": trace_id})
```

#### 4.4 Log Trace ID in Frontend

**File**: `frontend/src/lib/api.ts`
**Location**: Update the `ChatStreamEvent` interface

```typescript
export interface ChatStreamEvent {
    // ... existing fields
    trace_id?: string;  // Add this
}
```

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx`
**Location**: In the events handler

```typescript
} else if (event.type === "events" && event.events) {
    const traceId = event.trace_id || "unknown";
    debugLog("Events", "Received from backend", {
        trace: traceId,
        count: event.events.length
    });
    // ... rest of handler
```

### Success Criteria:

#### Automated Verification:
- [x] Backend type checking passes: `make -C api typecheck`
- [x] Backend tests pass: `make -C api test`
- [x] Frontend TypeScript compiles: `make -C frontend typecheck`
- [x] Frontend build succeeds: `make -C frontend build`

#### Manual Verification:
- [ ] Trigger a search with `LOG_LEVEL=DEBUG` backend and `DEBUG_EVENTS=true` frontend
- [ ] Find a trace ID in backend logs (e.g., `trace=a1b2c3d4`)
- [ ] Verify same trace ID appears in frontend console logs
- [ ] Can correlate backend event logging with frontend event reception

---

## Testing Strategy

### Unit Tests:
- No new unit tests required - this is logging/observability only
- Existing tests should continue to pass

### Integration Tests:
- Run full search flow with DEBUG logging enabled
- Verify all key log points emit expected output

### Manual Testing Steps:
1. Start backend: `LOG_LEVEL=DEBUG uv run uvicorn api.index:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Open browser console, run `localStorage.setItem('DEBUG_EVENTS', 'true')`
4. Trigger a search (e.g., "tech events this weekend")
5. Verify in backend logs:
   - Individual events logged from each source with `📋 [Search] Event from source`
   - Deduplication shows which events removed with `📋 [Dedup] Removed`
   - SSE streaming shows each event with `📋 [SSE] Streaming event`
   - Trace ID present in all logs
6. Verify in frontend console:
   - `[SSE] Event received` for each SSE event type
   - `[Events] Received from backend` with count and trace ID
   - Individual event details logged
7. Wait 15-30s and check for background results:
   - Backend logs show websets completion
   - Frontend logs show `[Events] Background discovery results` (if connection still open)

## Performance Considerations

- All new logging is DEBUG level - zero overhead in production
- Frontend logging gated by localStorage check - no performance impact when disabled
- Trace ID is 8 characters (UUID prefix) - minimal payload increase
- Individual event logging uses `logger.isEnabledFor(logging.DEBUG)` guard to avoid string formatting when DEBUG disabled

## Migration Notes

No migration required - this is additive logging with no behavior changes.

## References

- Research document: `thoughts/shared/research/2026-01-11-event-flow-logging-architecture.md`
- Emoji logging convention: `api/README.md:84-101`
- SSE implementation: `api/services/sse_connections.py`
- Frontend SSE client: `frontend/src/lib/api.ts:120-191`
- Event handlers: `frontend/src/components/discovery/DiscoveryChat.tsx:112-176`
