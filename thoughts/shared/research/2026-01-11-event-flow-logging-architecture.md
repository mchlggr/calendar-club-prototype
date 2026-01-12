---
date: 2026-01-11T23:47:00Z
researcher: Claude Code
git_commit: 936886e69700bb81dc760f3eaa0efc28c5ab6416
branch: main
repository: calendar-club-prototype
topic: "Event Flow, Logging Architecture, and Search Scoping"
tags: [research, codebase, events, logging, sse, integrations, search]
status: complete
last_updated: 2026-01-11
last_updated_by: Claude Code
---

# Research: Event Flow, Logging Architecture, and Search Scoping

**Date**: 2026-01-11T23:47:00Z
**Researcher**: Claude Code
**Git Commit**: 936886e69700bb81dc760f3eaa0efc28c5ab6416
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

How do events flow from backend integrations to the frontend? What logging exists? Where might events get lost? How are searches scoped by time and location?

## Summary

The system fetches events from 4 sources (Eventbrite, Exa, Posh, Meetup - though Meetup is not registered) in parallel, converts them to a unified format, deduplicates, and streams them to the frontend via SSE.

**Key Findings:**
1. **Backend logging shows counts only** - Individual events are never logged, only aggregate counts (e.g., "events=25")
2. **Frontend has minimal logging** - Only 4 console statements exist, all for errors/warnings
3. **Location is hardcoded** - All integrations default to "Columbus, OH" regardless of SearchProfile
4. **Time scoping works** - Time windows flow from clarifying agent through to API calls
5. **Potential loss points identified** - Events could be lost at deduplication, conversion errors, or SSE buffering

## Detailed Findings

### 1. Backend Logging Patterns

#### Current Emoji Logging System

The backend uses a structured emoji logging system documented at `api/README.md:84-101`:

| Emoji | Meaning | Usage |
|-------|---------|-------|
| 💬 | User message received | Chat endpoint |
| 🤔 | Agent processing | Clarifying agent |
| 🔍 | Search phase | Search handoff |
| 🌐 | External API call start | Integrations |
| ✅ | Success/completion | All completion points |
| ❌ | Error/failure | Error conditions |
| 📊 | Statistics (counts) | Aggregation points |
| 📤 | SSE streaming | Event streaming |
| 📭 | Empty results | No results found |

#### What IS Logged (Counts Only)

**Eventbrite** (`api/services/eventbrite.py:242-246`):
```python
logger.debug("✅ [Eventbrite] Complete | events=%d duration=%.2fs", len(events), elapsed)
```

**Search Agent** (`api/agents/search.py:300-304`):
```python
logger.debug("✅ [Search] Source complete | source=%s events=%d", source_name, len(converted))
```

**Deduplication** (`api/agents/search.py:321-326`):
```python
logger.debug("📊 [Search] Deduplication | before=%d after=%d removed=%d", ...)
```

**SSE Streaming** (`api/index.py:228-232`):
```python
logger.debug("📤 [SSE] Streaming events | session=%s count=%d", session_id, len(events_data))
```

#### What is NOT Logged

- **Individual event titles** - Never logged
- **Event times/dates** - Never logged
- **Event URLs** - Never logged
- **Conversion failures** - Only logged at warning level when exception raised

### 2. Frontend Logging Patterns

#### Total Console Statements: 4

All logging is for errors/warnings only. **No debug logging exists.**

1. `frontend/src/lib/telemetry.ts:26` - Missing HyperDX API key warning
2. `frontend/src/lib/posthog.ts:17` - Missing PostHog key warning
3. `frontend/src/components/discovery/ResultsPreview.tsx:87` - Export failure error
4. `frontend/src/app/week/page.tsx:39` - Session storage parse error

**No logging exists for:**
- Events received from backend
- Event mapping/transformation
- SSE stream parsing
- Component state updates

### 3. Data Flow Architecture

```
User Input
    ↓
POST /api/chat/stream (api/index.py:345)
    ↓
Clarifying Agent (api/agents/clarifying.py:141)
    ↓ [Extracts SearchProfile with time_window, categories, keywords]
search_events() (api/agents/search.py:223)
    ↓ [Parallel dispatch]
    ├─→ Eventbrite (api/services/eventbrite.py)
    ├─→ Exa (api/services/exa_client.py)
    └─→ Posh (api/services/firecrawl.py)
    ↓ [Results collected]
_convert_source_results() (api/agents/search.py:200)
    ↓ [Convert to unified EventResult format]
_deduplicate_events() (api/agents/search.py:174)
    ↓ [Remove duplicates by URL/title]
Sort & Limit to 15 events (api/agents/search.py:329-330)
    ↓
Transform to wire format (api/index.py:215-226)
    ↓
SSE Event: {"type": "events", "events": [...]}
    ↓
Frontend fetch() + ReadableStream (frontend/src/lib/api.ts:120)
    ↓
mapApiEventToCalendarEvent() (frontend/src/components/discovery/DiscoveryChat.tsx:45)
    ↓
UI Render (ResultsPreview, WeekView)
```

### 4. Potential Loss Points

#### A. Conversion Errors (Silent Failures)
`api/agents/search.py:214-219`:
```python
try:
    converted = converter(item)
    # ... add to results
except Exception as e:
    logger.warning("Error converting result from %s: %s", source_name, e)
```
Events that fail conversion are silently dropped with only a warning log.

#### B. Deduplication
`api/agents/search.py:174-191`:
- Duplicates removed by normalized URL or normalized title
- **Log shows count but not which events were removed**

#### C. 15 Event Limit
`api/agents/search.py:330`:
```python
unique_events = unique_events[:15]
```
Events beyond 15 are silently truncated.

#### D. SSE Parsing Errors
`frontend/src/lib/api.ts:174-178`:
```python
} catch (e) {
    if (e instanceof SyntaxError) {
        // Silently ignore JSON parsing errors
        continue;
    }
```
Malformed SSE events are silently dropped.

#### E. Date Parsing Failures
`frontend/src/components/discovery/DiscoveryChat.tsx:60-63`:
```typescript
const startTime = new Date(event.startTime);
const endTime = event.endTime ? new Date(event.endTime) : new Date(startTime.getTime() + 2 * 60 * 60 * 1000);
```
Invalid ISO strings could produce invalid Date objects (NaN), which would cause rendering issues.

### 5. Time/Location Scoping

#### Time Window Flow

1. **User input**: "this weekend" or "tonight"
2. **Clarifying agent** interprets via LLM instructions (`api/agents/clarifying.py:31-37`):
   - "this weekend" → Friday evening through Sunday night
   - "tonight" → 5pm onwards
3. **SearchProfile** created with `time_window.start` and `time_window.end` as ISO strings
4. **Each integration** extracts and applies time filters:

| Source | Time Filter Method |
|--------|-------------------|
| Eventbrite | Query params: `start_date.range_start`, `start_date.range_end` |
| Exa | Payload: `startPublishedDate`, `endPublishedDate` (date only) |
| Meetup | GraphQL: `startDateRange`, `endDateRange` |
| Posh | Client-side filtering after fetch |

#### Location Scoping (HARDCODED)

**All integrations use hardcoded Columbus, OH location:**

| Source | Location Code | File |
|--------|--------------|------|
| Eventbrite | `location = "Columbus, OH"` | `eventbrite.py:441` |
| Exa | `query_parts = ["events", "Columbus Ohio"]` | `exa_client.py:366` |
| Meetup | `latitude: 39.9612, longitude: -82.9988` | `meetup.py:142-143` |
| Posh | `city = "columbus"` | `firecrawl.py:383` |

**SearchProfile has location fields but they are unused:**
- `max_distance_miles: float | None` exists at `api/models/search.py:39-41`
- Never populated by clarifying agent
- Never extracted by any integration adapter

### 6. Event Source Registry

**Registered Sources** (`api/index.py:44-46`):
```python
register_eventbrite_source()  # Priority 10
register_exa_source()         # Priority 20
register_posh_source()        # Priority 25
```

**NOT Registered**: Meetup client exists at `api/services/meetup.py` but is not added to the registry. This means Meetup events are never fetched during normal search.

### 7. SSE Event Types

| Type | Purpose | Payload |
|------|---------|---------|
| `content` | Streaming text chunks | `{content: "..."}` |
| `searching` | Show loading indicator | `{}` |
| `quick_picks` | Dynamic suggestions | `{options: [...]}` |
| `placeholder` | Input placeholder | `{placeholder: "..."}` |
| `ready_to_search` | Clarification complete | `{}` |
| `events` | Search results | `{events: [...]}` |
| `more_events` | Background results | `{events: [...], source: "webset"}` |
| `done` | Stream complete | `{}` |
| `error` | Error message | `{message: "..."}` |

## Code References

### Backend Event Discovery
- `api/services/base.py:47-124` - EventSourceRegistry
- `api/agents/search.py:223-344` - Search orchestration
- `api/services/eventbrite.py:428-469` - Eventbrite adapter
- `api/services/exa_client.py:353-405` - Exa adapter
- `api/services/firecrawl.py:370-407` - Posh adapter

### Backend Logging
- `api/README.md:84-101` - Emoji logging documentation
- `api/index.py:228-232` - SSE streaming log
- `api/agents/search.py:300-326` - Source completion and deduplication logs

### Frontend Event Display
- `frontend/src/lib/api.ts:120-191` - SSE streaming client
- `frontend/src/components/discovery/DiscoveryChat.tsx:45-75` - Event mapping
- `frontend/src/components/discovery/DiscoveryChat.tsx:112-176` - Event handling

### Search Scoping
- `api/models/search.py:23-45` - SearchProfile model
- `api/agents/clarifying.py:31-37` - Time interpretation instructions
- `api/services/temporal_parser.py:112-132` - Weekend calculation

## Architecture Documentation

### Logging Configuration
- Debug logging enabled via: `LOG_LEVEL=DEBUG uv run uvicorn api.index:app --reload`
- Log format: `"emoji [Component] Description | key1=value1 key2=value2"`
- Error messages truncated to 100 chars to prevent log spam

### Integration Priorities
Lower priority = queried first:
1. Eventbrite (10) - Structured event data
2. Exa (20) - Neural web search
3. Posh (25) - Scraping (slowest)

### Timeouts
- Eventbrite: 30s
- Exa: 30s
- Posh/Firecrawl: 60s
- SSE queue poll: 0.5s

## Open Questions

1. **Why isn't Meetup registered?** - Client exists but not in registry
2. **Should location be dynamic?** - Currently hardcoded to Columbus
3. **What causes poor result quality?** - Need individual event logging to diagnose
4. **Are events being filtered incorrectly?** - Need to log time window application per source
