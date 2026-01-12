---
date: 2026-01-09T15:04:06-0500
researcher: michaelgeiger
git_commit: c57e342f1ee87a6c654c504004e48175f4e9dabf
branch: main
repository: calendar-club-prototype
topic: "Production Readiness Analysis - Identifying Gaps and Disconnected Systems"
tags: [research, production-readiness, gaps, mock-data, integration]
status: complete
last_updated: 2026-01-09
last_updated_by: michaelgeiger
---

# Research: Production Readiness Analysis

**Date**: 2026-01-09T15:04:06-0500
**Researcher**: michaelgeiger
**Git Commit**: c57e342f1ee87a6c654c504004e48175f4e9dabf
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

What are the gaps between the current implementation and production readiness for early users? Where is mock data, what's disconnected, and what fell through the cracks?

## Executive Summary

Calendar Club is approximately **60% complete** for an early-user MVP. The conversational UI flow is well-built, but the core value proposition—discovering real events—is currently mocked. The system has three critical gaps:

1. **No Real Event Data** - All events are hardcoded mock data
2. **No Authentication** - Anonymous-only, no user accounts
3. **Frontend-Backend Disconnect** - Frontend uses local mock data, not the streaming API

## Gap Analysis Overview

| Category | Current State | Production Need | Gap Severity |
|----------|---------------|-----------------|--------------|
| **Event Data** | Mock data (5 events) | Real API integrations | 🔴 Critical |
| **Frontend-Backend Connection** | Disconnected | Streaming chat integration | 🔴 Critical |
| **Authentication** | None | User accounts | 🟡 Medium |
| **Database** | Session-only SQLite | Event storage, user data | 🟡 Medium |
| **Calendar Export** | Not implemented | ICS download, webcal | 🟡 Medium |
| **Error Handling** | Minimal | Production-grade | 🟡 Medium |
| **Environment Config** | Hardcoded values | Environment-based | 🟢 Low |

---

## Critical Gap 1: Mock Event Data

### Current State

**Backend Mock Data** (`backend/agents/search.py:57-91`)

The `search_events` function returns hardcoded mock events with a TODO comment at line 54:
```python
# TODO: Implement actual search against event sources
```

Mock events returned:
- `evt-001`: Columbus AI Meetup (Industrious Columbus)
- `evt-002`: Startup Weekend Columbus (Rev1 Ventures)
- `evt-003`: Tech on Tap (Land-Grant Brewing)
- `evt-004`: Python Columbus (CoverMyMeds HQ) - from refine_results
- `evt-005`: Data Science Happy Hour (Brewdog Short North) - from refine_results

**Frontend Mock Data** (`frontend/src/app/week/page.tsx:14-59`)

The WeekView page has its own independent mock data:
```typescript
const mockEvents: CalendarEvent[] = [
  // 4 hardcoded events with computed timestamps
]
```

**Frontend Discovery Mock** (`frontend/src/components/discovery/DiscoveryChat.tsx:98-132`)

The discovery flow also generates mock results after a simulated 1.5s delay:
```typescript
// Simulated search delay
await new Promise(resolve => setTimeout(resolve, 1500));
const mockResults = [...]; // 3 hardcoded events
```

### What's Needed

1. **Event Source API Integrations** - Connect to:
   - Eventbrite API (documented in research)
   - Meetup GraphQL API (documented in research)
   - Luma API (requires subscription)

2. **Event Storage** - Database for:
   - Caching API responses
   - Deduplication
   - User ratings/feedback

3. **Search Implementation** - Replace mock `search_events` tool with real queries

### Files to Modify

- `backend/agents/search.py:43-91` - Replace mock with real API calls
- `backend/agents/search.py:140-163` - Replace mock refinement results
- New file needed: `backend/services/event_sources/` - API connectors
- New file needed: `backend/models/event.py` - Event database model

---

## Critical Gap 2: Frontend-Backend Disconnect

### Current State

The frontend and backend are built separately and **do not communicate**:

**Frontend Discovery Flow** (`frontend/src/components/discovery/DiscoveryChat.tsx`)
- Handles all state locally
- Uses `setTimeout` to simulate API delay (line 136)
- Returns mock results, never calls backend
- No fetch/API calls to `/chat/stream`

**Backend Streaming API** (`backend/main.py:52-106`)
- Fully implemented SSE streaming endpoint
- Agents work correctly (ClarifyingAgent → SearchAgent handoff)
- Session persistence via SQLite
- **Never called by frontend**

**Frontend API Client** (`frontend/src/lib/api.ts`)
- Well-built with retry logic and date serialization
- Endpoints defined: `/api/chat`, `/api/events`, `/api/search`
- **Not used by DiscoveryChat component**

### Evidence of Disconnect

| Frontend Component | Expected Behavior | Actual Behavior |
|-------------------|-------------------|-----------------|
| `DiscoveryChat.tsx:51-65` | Call `api.chat()` | Just updates local state |
| `DiscoveryChat.tsx:77-138` | Stream results from backend | Uses `setTimeout` + mock data |
| `ResultsPreview.tsx` | Display API results | Displays mock array |
| `WeekView` | Fetch events for date range | Uses hardcoded `mockEvents` |

### Integration Work Needed

1. **Connect DiscoveryChat to Streaming API**
   - Replace `handleSubmit` to call `/chat/stream` endpoint
   - Parse SSE events for `text`, `phase`, `action`, `complete`
   - Handle agent handoff events (ClarifyingAgent → SearchAgent)

2. **Wire Up Event Fetching**
   - Replace `mockEvents` in `week/page.tsx` with `useEvents()` hook
   - Pass `weekStart` date range to API

3. **Implement Missing API Endpoints**
   - GET `/api/events` - Not implemented in backend
   - POST `/api/search` - Not implemented in backend

### Files to Modify

- `frontend/src/components/discovery/DiscoveryChat.tsx` - Add streaming fetch
- `frontend/src/app/week/page.tsx` - Replace mockEvents with API call
- `backend/main.py` - Add `/events` and `/search` endpoints
- `frontend/src/lib/hooks.ts` - Hooks exist but unused

---

## Medium Gap 3: No Authentication System

### Current State

The application has **zero authentication**:

- No user models or accounts
- No login/signup flows
- No protected routes
- Session IDs generated client-side (UUID in localStorage)
- Backend accepts any session_id without validation

**Current Session Flow**:
```
Browser → crypto.randomUUID() → localStorage → Send to backend
Backend → Create SQLiteSession(any_session_id) → No validation
```

### What's Needed for Early Users

At minimum:
1. **Anonymous persistence** - Already works via session_id
2. **Optional account creation** - Save preferences across devices
3. **Calendar integration auth** - OAuth for Google/Microsoft calendar sync

Recommended approach (per TECHSTACK.md):
- Start with anonymous + localStorage
- Add auth when users request saved preferences
- Use NextAuth.js or similar for OAuth

### Files to Create

- `frontend/src/app/login/page.tsx`
- `frontend/src/app/api/auth/[...nextauth]/route.ts` (if using NextAuth)
- `backend/models/user.py`
- `backend/services/auth.py`

---

## Medium Gap 4: Minimal Database/Persistence

### Current State

**Only SQLite for chat sessions**:
- `conversations.db` stores conversation history
- Uses OpenAI Agents SDK's `SQLiteSession`
- No event storage, user data, or preferences

**What's NOT Persisted**:
- Event data (all from APIs or mocks)
- User preferences/ratings
- Search history
- Favorites/saved events

### What's Needed

1. **Event Cache** - Store API responses to reduce rate limits
2. **User Feedback** - Save Yes/No/Maybe ratings
3. **Search Preferences** - Remember location, categories, etc.

### Files to Create

- `backend/models/event.py` - Event model
- `backend/models/feedback.py` - User feedback model
- `backend/services/database.py` - Database connection
- Migration scripts

---

## Medium Gap 5: Calendar Export Not Implemented

### Current State

Research is complete (`throughts/research/2025-01-09-calendar-export-integration.md`) but no code exists:

- No ICS generation
- No webcal subscription feeds
- No Google Calendar OAuth integration
- No Microsoft Graph integration

### What's Needed for MVP

**Phase 3a (Minimum)**:
1. Single event ICS download button
2. `icalendar` Python library integration

**Phase 3b (Stretch)**:
1. Webcal subscription URLs
2. OAuth flows for direct calendar add

### Files to Create

- `backend/services/calendar.py` - ICS generation
- `backend/routes/calendar.py` - Export endpoints
- `frontend/src/components/calendar/ExportButton.tsx`

---

## Medium Gap 6: Error Handling Incomplete

### Current State

**Backend** (`backend/main.py:95-97`):
```python
except Exception as e:
    yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
```
- Generic error message sent to client
- No error codes or recovery suggestions
- No logging beyond HyperDX

**Frontend** (`frontend/src/lib/api.ts:84-103`):
- `ApiError` and `NetworkError` classes defined
- Retry logic for 5xx errors
- **No error UI components**

### What's Needed

1. **Error boundaries** - Graceful failure states
2. **Toast notifications** - User-friendly error messages
3. **Retry UI** - "Try again" buttons
4. **Structured error codes** - Machine-readable errors

---

## Low Gap 7: Environment Configuration

### Current State

**Hardcoded Values Found**:
- Columbus, OH as default location (`backend/agents/clarifying.py:23`)
- "847 events" placeholder (`frontend/src/components/discovery/DiscoveryChat.tsx:195`)
- `gpt-4o` model hardcoded (`backend/agents/*.py`)
- Timezone "America/New_York" (`backend/services/temporal.py:30`)

**Missing .env.example**:
- No `.env.example` file for documentation
- Required variables not documented

### Quick Fixes

1. Create `.env.example` with all required variables
2. Move hardcoded values to environment/config
3. Document required secrets in README

---

## Detailed Code References

### Mock Data Locations

| File | Lines | Mock Type |
|------|-------|-----------|
| `backend/agents/search.py` | 57-91 | Search results (3 events) |
| `backend/agents/search.py` | 140-163 | Refinement results (2 events) |
| `frontend/src/app/week/page.tsx` | 14-59 | Week view events (4 events) |
| `frontend/src/components/discovery/DiscoveryChat.tsx` | 98-132 | Discovery results (3 events) |
| `frontend/src/components/discovery/DiscoveryChat.tsx` | 195 | "847 events" count |

### TODO Comments in Codebase

| File | Line | Comment |
|------|------|---------|
| `backend/agents/search.py` | 54 | `# TODO: Implement actual search against event sources` |

### Unused/Stubbed Code

| File | Lines | Description |
|------|-------|-------------|
| `frontend/src/lib/api.ts` | 266-314 | `api.getEvents()` and `api.search()` defined but unused |
| `frontend/src/lib/hooks.ts` | 41-136 | React Query hooks defined but unused |
| `frontend/src/app/share/[id]/page.tsx` | All | Placeholder "coming soon" page |

---

## Recommended Priority Order

### Phase 1: Connect Frontend to Backend (Required for MVP)

1. Wire `DiscoveryChat` to call `/chat/stream` endpoint
2. Parse SSE stream and update UI in real-time
3. Handle agent handoff events (phase changes)
4. Connect week view to fetch real data

**Estimated files**: 3-4 files modified

### Phase 2: Real Event Data (Required for MVP)

1. Implement at least ONE event source (Eventbrite or Meetup)
2. Replace mock `search_events` with real API calls
3. Add basic event caching

**Estimated files**: 4-6 new files

### Phase 3: Calendar Export (High Value)

1. Add ICS download button
2. Generate valid iCalendar files
3. Test with Apple Calendar, Google Calendar, Outlook

**Estimated files**: 2-3 new files

### Phase 4: Polish (Pre-Launch)

1. Error boundaries and toast notifications
2. Loading states and skeleton UI
3. Environment configuration cleanup
4. `.env.example` documentation

---

## Architecture Diagram: Current vs Target

### Current State

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND                                │
│  ┌──────────────┐    ┌─────────────┐    ┌──────────────┐   │
│  │DiscoveryChat │    │  WeekView   │    │   api.ts     │   │
│  │ (mock data)  │    │ (mock data) │    │  (unused)    │   │
│  └──────────────┘    └─────────────┘    └──────────────┘   │
│           ↓                  ↓                  ↓           │
│    setTimeout 1.5s     mockEvents[]       Not called        │
└─────────────────────────────────────────────────────────────┘
                              ✗ DISCONNECTED
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND                                 │
│  ┌──────────────┐    ┌─────────────┐    ┌──────────────┐   │
│  │/chat/stream  │    │ClarifyAgent │    │ SearchAgent  │   │
│  │   (works)    │───→│  (works)    │───→│ (mock data)  │   │
│  └──────────────┘    └─────────────┘    └──────────────┘   │
│           ↓                                    ↓            │
│    SQLiteSession                        hardcoded[]         │
└─────────────────────────────────────────────────────────────┘
```

### Target State

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND                                │
│  ┌──────────────┐    ┌─────────────┐    ┌──────────────┐   │
│  │DiscoveryChat │    │  WeekView   │    │   api.ts     │   │
│  │   (live)     │    │   (live)    │    │  (active)    │   │
│  └──────┬───────┘    └──────┬──────┘    └──────┬───────┘   │
│         │                   │                   │           │
│         └───────────────────┴───────────────────┘           │
│                             ↓                               │
│                     fetch('/api/...')                       │
└─────────────────────────────────────────────────────────────┘
                              ↓ CONNECTED
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND                                 │
│  ┌──────────────┐    ┌─────────────┐    ┌──────────────┐   │
│  │/chat/stream  │    │ClarifyAgent │    │ SearchAgent  │   │
│  │/api/events   │───→│             │───→│              │   │
│  └──────────────┘    └─────────────┘    └──────┬───────┘   │
│           ↓                                    ↓            │
│    SQLiteSession                        EventSourceAPI      │
│                                         ┌──────────────┐   │
│                                         │ Eventbrite   │   │
│                                         │ Meetup       │   │
│                                         │ Luma         │   │
│                                         └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Open Questions

1. **Which event source to prioritize?** Eventbrite has best docs, Meetup has GraphQL, Luma requires subscription
2. **Authentication timing?** Add before or after event source integration?
3. **Columbus-only MVP?** Keep hardcoded location or make configurable?
4. **Hosting strategy?** Vercel for frontend + what for backend?

---

## Related Research

- `throughts/research/2025-01-09-calendar-export-integration.md` - Calendar API integration
- `throughts/research/Key Event API Sources and Their Limits.md` - Event source APIs
- `TECHSTACK.md` - Architecture decisions and rationale
- `ROADMAP.md` - Feature roadmap

---

## Appendix: Full File Inventory

### Backend Files
- `backend/main.py` - FastAPI application
- `backend/agents/clarifying.py` - Discovery agent
- `backend/agents/search.py` - Search agent with mock data
- `backend/models/search.py` - Pydantic models
- `backend/services/session.py` - Session management
- `backend/services/temporal.py` - Date parsing

### Frontend Files
- `frontend/src/app/page.tsx` - Home page
- `frontend/src/app/week/page.tsx` - Week view with mock data
- `frontend/src/components/discovery/DiscoveryChat.tsx` - Main chat with mock data
- `frontend/src/components/discovery/ResultsPreview.tsx` - Results display
- `frontend/src/components/calendar/WeekView.tsx` - Calendar component
- `frontend/src/lib/api.ts` - API client (unused)
- `frontend/src/lib/hooks.ts` - React Query hooks (unused)
