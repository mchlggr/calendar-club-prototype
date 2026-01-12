# Calendar Club Production Readiness Implementation Plan

## Overview

This plan addresses the gaps identified in the production readiness research to make Calendar Club ready for early users. The system currently has a working streaming chat flow, but event data is mocked throughout. We'll implement real event data, complete the data flow, and add calendar export functionality.

## Current State Analysis

### What Works
- **Streaming chat**: Frontend calls `api.chatStream()` → Backend `/chat/stream` endpoint streams responses
- **Agent handoff**: ClarifyingAgent → SearchAgent handoff works correctly
- **Session persistence**: SQLite-backed conversation history via OpenAI Agents SDK
- **UI components**: Discovery flow, week view, event cards all render correctly
- **Telemetry**: HyperDX integration tracks user behavior

### What's Broken/Incomplete
1. **Event data is mock everywhere**: Backend returns hardcoded events, frontend also uses separate mock data
2. **Event results not streamed**: When SearchAgent calls `search_events`, results aren't sent to frontend
3. **Week view disconnected**: Uses local `mockEvents` array, not discovery results
4. **No real event sources**: No Eventbrite, Meetup, or other API integration

### Key Discoveries
- `DiscoveryChat.tsx:147` already calls `api.chatStream()` - connection exists
- `DiscoveryChat.tsx:82-116` shows mock results after stream - needs real data
- `backend/main.py:86-90` streams tool call events but not results
- `backend/agents/search.py:54` has TODO for real search implementation
- Eventbrite API: 2000 req/hr limit, good documentation

## Desired End State

After implementation:
1. User types "AI meetups this weekend" → Sees real Eventbrite/Meetup events
2. Events from discovery flow appear in Week View
3. Users can download .ics files for any event
4. No mock data anywhere in production flow

**Verification**: Search for "Columbus AI meetups" - results should be real events with working RSVP links

## What We're NOT Doing

- User authentication (anonymous first, auth later)
- Google/Microsoft calendar OAuth integration (ICS download only)
- Multiple event source aggregation (one source first, then expand)
- Full-text search across event descriptions (API search only)
- Event caching/database (direct API calls, cache later if needed)

## Implementation Approach

We'll work in 4 phases:
1. **Phase 1**: Stream event results from backend → frontend (complete the data flow)
2. **Phase 2**: Integrate one real event source (Eventbrite)
3. **Phase 3**: Add ICS calendar export
4. **Phase 4**: Connect Week View and polish

Each phase is independently testable and deployable.

---

## Phase 1: Complete the Streaming Data Flow

### Overview

The frontend connects to the backend but doesn't receive event results from the SearchAgent's tool calls. We need to:
1. Stream `EventResult` data when `search_events` tool runs
2. Parse event data on frontend and display real results
3. Remove mock data fallbacks

### Changes Required

#### 1.1 Backend: Stream Event Results

**File**: `backend/main.py`

Add event result streaming when tool calls complete:

```python
# Around line 86-90, expand the tool call handling:
elif event.type == "run_item_stream_event":
    if hasattr(event.item, "type"):
        if event.item.type == "tool_call_item":
            tool_name = getattr(event.item, "name", "unknown")
            yield f"data: {json.dumps({'type': 'action', 'tool': tool_name})}\n\n"
        elif event.item.type == "tool_call_output_item":
            # Stream the tool output (event results)
            output = getattr(event.item, "output", None)
            if output:
                yield f"data: {json.dumps({'type': 'events', 'data': output})}\n\n"
```

#### 1.2 Frontend: Parse Event Stream

**File**: `frontend/src/lib/api.ts`

Update `ChatStreamEvent` type to include events:

```typescript
export interface ChatStreamEvent {
    type: "content" | "done" | "error" | "events" | "action" | "phase";
    content?: string;
    error?: string;
    session_id?: string;
    data?: EventResult[];  // Add events data
}

export interface EventResult {
    id: string;
    title: string;
    date: string;
    location: string;
    category: string;
    description: string;
    is_free: boolean;
    price_amount?: number;
    distance_miles: number;
}
```

#### 1.3 Frontend: Handle Event Data in DiscoveryChat

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx`

Replace mock data handling with real event parsing:

```typescript
// In startChatStream function, around line 62-131:
const handleChunk = (event: ChatStreamEvent) => {
    if (event.type === "content" && event.content) {
        setStreamingMessage((prev) => prev + event.content);
    } else if (event.type === "events" && event.data) {
        // Convert EventResult to CalendarEvent
        const events = event.data.map(transformEventResult);
        setPendingResults(events);
    } else if (event.type === "done") {
        // Move streaming message to messages
        setStreamingMessage((prev) => {
            if (prev) {
                setMessages((msgs) => [...msgs, {
                    id: crypto.randomUUID(),
                    role: "agent",
                    content: prev,
                }]);
            }
            return "";
        });
        // Use pendingResults instead of mock data
        onResultsReady(pendingResults);
        setState("results");
    }
    // ... error handling
};
```

Add transform function:

```typescript
function transformEventResult(result: EventResult): CalendarEvent {
    return {
        id: result.id,
        title: result.title,
        startTime: new Date(result.date),
        endTime: new Date(new Date(result.date).getTime() + 2 * 60 * 60 * 1000), // +2 hours
        category: result.category as CalendarEvent["category"],
        venue: result.location,
        neighborhood: "", // Not in EventResult yet
        canonicalUrl: `https://eventbrite.com/e/${result.id}`, // Will be real URL in Phase 2
        sourceId: result.id,
    };
}
```

#### 1.4 Remove Mock Data

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx`

Delete lines 82-116 (the mock results array and its usage).

### Success Criteria

#### Automated Verification
- [ ] Backend starts without errors: `uv run uvicorn backend.main:app --reload`
- [ ] Frontend builds without errors: `cd frontend && npm run build`
- [ ] TypeScript passes: `cd frontend && npm run typecheck` (if script exists)

#### Manual Verification
- [ ] Send a message in discovery chat
- [ ] See events appear after SearchAgent runs (even if mock, they come from backend)
- [ ] No "hardcoded" arrays visible in browser dev tools network tab
- [ ] Events display correctly in ResultsPreview

**Implementation Note**: After completing Phase 1, pause for manual confirmation before proceeding.

---

## Phase 2: Real Event Data (Eventbrite Integration)

### Overview

Replace mock data in `search_events` with real Eventbrite API calls. Eventbrite offers:
- 2,000 requests/hour, 48,000/day
- Good search endpoints
- Event details including location, pricing, dates

### Changes Required

#### 2.1 Environment Configuration

**File**: `.env`

Add Eventbrite API key:

```
EVENTBRITE_API_KEY=your_eventbrite_api_key_here
```

**File**: `.env.example` (create)

```
# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Eventbrite API
EVENTBRITE_API_KEY=your_eventbrite_api_key

# HyperDX Telemetry (optional)
NEXT_PUBLIC_HYPERDX_API_KEY=local
NEXT_PUBLIC_HYPERDX_ENDPOINT=http://localhost:4318
```

#### 2.2 Create Eventbrite Client

**File**: `backend/services/eventbrite.py` (new file)

```python
"""
Eventbrite API client for event search.
"""

import os
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel

EVENTBRITE_BASE_URL = "https://www.eventbriteapi.com/v3"


class EventbriteEvent(BaseModel):
    """Event from Eventbrite API."""
    id: str
    name: str
    description: str | None
    start_local: str
    end_local: str | None
    venue_name: str | None
    venue_address: str | None
    is_free: bool
    url: str
    category_name: str | None


class EventbriteClient:
    """Client for Eventbrite API."""

    def __init__(self):
        self.api_key = os.getenv("EVENTBRITE_API_KEY")
        if not self.api_key:
            raise ValueError("EVENTBRITE_API_KEY environment variable not set")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def search_events(
        self,
        query: str | None = None,
        location: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        categories: list[str] | None = None,
        free_only: bool = False,
    ) -> list[EventbriteEvent]:
        """
        Search for events on Eventbrite.

        Args:
            query: Search query string
            location: Location string (city, address, etc.)
            start_date: Start of date range
            end_date: End of date range
            categories: List of category filters
            free_only: Only return free events

        Returns:
            List of matching events
        """
        params: dict[str, Any] = {
            "expand": "venue,category",
        }

        if query:
            params["q"] = query
        if location:
            params["location.address"] = location
        if start_date:
            params["start_date.range_start"] = start_date.isoformat()
        if end_date:
            params["start_date.range_end"] = end_date.isoformat()
        if free_only:
            params["price"] = "free"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{EVENTBRITE_BASE_URL}/events/search/",
                params=params,
                headers=self.headers,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        events = []
        for event_data in data.get("events", []):
            venue = event_data.get("venue", {}) or {}
            category = event_data.get("category", {}) or {}

            events.append(EventbriteEvent(
                id=event_data["id"],
                name=event_data["name"]["text"],
                description=event_data.get("description", {}).get("text"),
                start_local=event_data["start"]["local"],
                end_local=event_data.get("end", {}).get("local"),
                venue_name=venue.get("name"),
                venue_address=venue.get("address", {}).get("localized_address_display"),
                is_free=event_data.get("is_free", False),
                url=event_data["url"],
                category_name=category.get("name"),
            ))

        return events


# Module-level client (lazy initialization)
_client: EventbriteClient | None = None


def get_eventbrite_client() -> EventbriteClient:
    """Get or create the Eventbrite client."""
    global _client
    if _client is None:
        _client = EventbriteClient()
    return _client
```

#### 2.3 Update Search Tool

**File**: `backend/agents/search.py`

Replace mock data with real API call:

```python
import asyncio
from backend.services.eventbrite import get_eventbrite_client, EventbriteEvent


def _map_eventbrite_to_result(event: EventbriteEvent) -> EventResult:
    """Convert Eventbrite event to our EventResult format."""
    return EventResult(
        id=event.id,
        title=event.name,
        date=event.start_local,
        location=event.venue_name or event.venue_address or "Online",
        category=_categorize_event(event),
        description=event.description or "",
        is_free=event.is_free,
        price_amount=None,  # Would need separate API call for pricing
        distance_miles=0.0,  # Would need geocoding for distance
    )


def _categorize_event(event: EventbriteEvent) -> str:
    """Map Eventbrite category to our categories."""
    category_map = {
        "Science & Technology": "ai",
        "Business & Professional": "startup",
        "Community & Culture": "community",
    }
    return category_map.get(event.category_name or "", "community")


@function_tool
def search_events(profile: SearchProfile) -> list[EventResult]:
    """
    Search for events matching the profile.
    """
    try:
        client = get_eventbrite_client()

        # Parse date window
        start_date = None
        end_date = None
        if profile.date_window:
            from datetime import datetime
            start_date = datetime.fromisoformat(profile.date_window.start)
            end_date = datetime.fromisoformat(profile.date_window.end)

        # Build query from categories
        query = " ".join(profile.categories) if profile.categories else None

        # Run async search in sync context
        events = asyncio.run(client.search_events(
            query=query,
            location=profile.location or "Columbus, OH",
            start_date=start_date,
            end_date=end_date,
            free_only=profile.constraints.free_only if profile.constraints else False,
        ))

        return [_map_eventbrite_to_result(e) for e in events[:10]]

    except Exception as e:
        # Fallback to mock data if API fails
        print(f"Eventbrite API error: {e}")
        return _get_fallback_events()


def _get_fallback_events() -> list[EventResult]:
    """Return fallback events if API fails."""
    return [
        EventResult(
            id="fallback-001",
            title="Unable to fetch events",
            date="2026-01-10T18:00:00",
            location="Try again later",
            category="community",
            description="We couldn't connect to our event sources. Please try again.",
            is_free=True,
            price_amount=None,
            distance_miles=0.0,
        ),
    ]
```

#### 2.4 Update EventResult Model for URLs

**File**: `backend/agents/search.py`

Add `url` field to `EventResult`:

```python
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
    url: str | None = None  # Add this field
```

Update the mapping function to include the URL:

```python
def _map_eventbrite_to_result(event: EventbriteEvent) -> EventResult:
    return EventResult(
        # ... existing fields ...
        url=event.url,
    )
```

#### 2.5 Frontend: Use Real URLs

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx`

Update transform function to use real URL:

```typescript
function transformEventResult(result: EventResult): CalendarEvent {
    return {
        // ... existing fields ...
        canonicalUrl: result.url || `https://eventbrite.com/e/${result.id}`,
    };
}
```

#### 2.6 Add httpx Dependency

**File**: `pyproject.toml`

Add to dependencies:

```toml
dependencies = [
    # ... existing deps ...
    "httpx>=0.27.0",
]
```

Then run: `uv sync`

### Success Criteria

#### Automated Verification
- [ ] `uv sync` completes without errors
- [ ] Backend starts: `uv run uvicorn backend.main:app --reload`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] No import errors in backend logs

#### Manual Verification
- [ ] Set `EVENTBRITE_API_KEY` in `.env`
- [ ] Search for "AI meetups Columbus" - see real Eventbrite events
- [ ] Click an event - opens real Eventbrite page
- [ ] Event details (venue, time, price) match Eventbrite listing
- [ ] Free events filter works

**Implementation Note**: After completing Phase 2, pause for manual confirmation before proceeding.

---

## Phase 3: Calendar Export (ICS Download)

### Overview

Add ability to download events as .ics files for import into any calendar app. This is a high-value feature that enables users to actually use the events they discover.

### Changes Required

#### 3.1 Install icalendar Library

**File**: `pyproject.toml`

```toml
dependencies = [
    # ... existing deps ...
    "icalendar>=6.0.0",
]
```

Run: `uv sync`

#### 3.2 Create Calendar Service

**File**: `backend/services/calendar.py` (new file)

```python
"""
Calendar export service for generating ICS files.
"""

from datetime import datetime
from typing import Any

from icalendar import Calendar, Event
from pydantic import BaseModel


class CalendarEventData(BaseModel):
    """Event data for calendar export."""
    id: str
    title: str
    description: str | None = None
    start: datetime
    end: datetime | None = None
    location: str | None = None
    url: str | None = None


def create_ics_event(event: CalendarEventData) -> str:
    """
    Create an ICS file for a single event.

    Args:
        event: Event data to export

    Returns:
        ICS file content as string
    """
    cal = Calendar()
    cal.add("prodid", "-//Calendar Club//calendarclub.io//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    ical_event = Event()
    ical_event.add("uid", f"{event.id}@calendarclub.io")
    ical_event.add("summary", event.title)
    ical_event.add("dtstart", event.start)

    if event.end:
        ical_event.add("dtend", event.end)
    else:
        # Default to 2 hours if no end time
        from datetime import timedelta
        ical_event.add("dtend", event.start + timedelta(hours=2))

    if event.description:
        ical_event.add("description", event.description)

    if event.location:
        ical_event.add("location", event.location)

    if event.url:
        ical_event.add("url", event.url)

    ical_event.add("dtstamp", datetime.utcnow())

    cal.add_component(ical_event)

    return cal.to_ical().decode("utf-8")


def create_ics_multiple(events: list[CalendarEventData]) -> str:
    """
    Create an ICS file with multiple events.

    Args:
        events: List of events to export

    Returns:
        ICS file content as string
    """
    cal = Calendar()
    cal.add("prodid", "-//Calendar Club//calendarclub.io//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Calendar Club Events")

    for event in events:
        ical_event = Event()
        ical_event.add("uid", f"{event.id}@calendarclub.io")
        ical_event.add("summary", event.title)
        ical_event.add("dtstart", event.start)

        if event.end:
            ical_event.add("dtend", event.end)
        else:
            from datetime import timedelta
            ical_event.add("dtend", event.start + timedelta(hours=2))

        if event.description:
            ical_event.add("description", event.description)
        if event.location:
            ical_event.add("location", event.location)
        if event.url:
            ical_event.add("url", event.url)

        ical_event.add("dtstamp", datetime.utcnow())
        cal.add_component(ical_event)

    return cal.to_ical().decode("utf-8")
```

#### 3.3 Add Calendar Export Endpoints

**File**: `backend/main.py`

Add new endpoints:

```python
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import Response

from backend.services.calendar import CalendarEventData, create_ics_event, create_ics_multiple


class ExportEventRequest(BaseModel):
    """Request body for single event export."""
    id: str
    title: str
    description: str | None = None
    start: str  # ISO 8601
    end: str | None = None
    location: str | None = None
    url: str | None = None


class ExportEventsRequest(BaseModel):
    """Request body for multiple events export."""
    events: list[ExportEventRequest]


@app.post("/calendar/export")
async def export_single_event(request: ExportEventRequest) -> Response:
    """
    Export a single event as an ICS file.

    Returns downloadable .ics file.
    """
    try:
        event = CalendarEventData(
            id=request.id,
            title=request.title,
            description=request.description,
            start=datetime.fromisoformat(request.start),
            end=datetime.fromisoformat(request.end) if request.end else None,
            location=request.location,
            url=request.url,
        )

        ics_content = create_ics_event(event)

        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="{event.title[:30]}.ics"',
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/calendar/export-multiple")
async def export_multiple_events(request: ExportEventsRequest) -> Response:
    """
    Export multiple events as a single ICS file.

    Returns downloadable .ics file.
    """
    try:
        events = [
            CalendarEventData(
                id=e.id,
                title=e.title,
                description=e.description,
                start=datetime.fromisoformat(e.start),
                end=datetime.fromisoformat(e.end) if e.end else None,
                location=e.location,
                url=e.url,
            )
            for e in request.events
        ]

        ics_content = create_ics_multiple(events)

        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": 'attachment; filename="calendar-club-events.ics"',
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

#### 3.4 Frontend: Add Export API Method

**File**: `frontend/src/lib/api.ts`

Add export function:

```typescript
export interface ExportEventRequest {
    id: string;
    title: string;
    description?: string;
    start: string;
    end?: string;
    location?: string;
    url?: string;
}

export const api = {
    // ... existing methods ...

    /**
     * POST /calendar/export - Download single event as ICS
     */
    async exportEvent(event: ExportEventRequest): Promise<void> {
        const baseUrl = getBaseUrl();
        const response = await fetch(`${baseUrl}/calendar/export`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(event),
        });

        if (!response.ok) {
            throw new ApiError("Export failed", response.status);
        }

        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${event.title.slice(0, 30)}.ics`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    },

    /**
     * POST /calendar/export-multiple - Download multiple events as ICS
     */
    async exportEvents(events: ExportEventRequest[]): Promise<void> {
        const baseUrl = getBaseUrl();
        const response = await fetch(`${baseUrl}/calendar/export-multiple`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ events }),
        });

        if (!response.ok) {
            throw new ApiError("Export failed", response.status);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "calendar-club-events.ics";
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    },
};
```

#### 3.5 Frontend: Add Export Button to ResultsPreview

**File**: `frontend/src/components/discovery/ResultsPreview.tsx`

Add export button:

```typescript
import { Calendar, Download } from "lucide-react";
import { api } from "@/lib/api";

// In the component, add handler:
const handleExportAll = async () => {
    const exportEvents = events.map(event => ({
        id: event.id,
        title: event.title,
        start: event.startTime.toISOString(),
        end: event.endTime?.toISOString(),
        location: event.venue,
        url: event.canonicalUrl,
    }));
    await api.exportEvents(exportEvents);
};

// In the JSX, add button alongside "View full week":
<button
    onClick={handleExportAll}
    className="flex items-center gap-2 rounded-lg border border-brand-green px-4 py-2 text-sm font-medium text-brand-green hover:bg-brand-green hover:text-white transition-colors"
>
    <Download className="h-4 w-4" />
    Add all to calendar
</button>
```

### Success Criteria

#### Automated Verification
- [ ] `uv sync` completes without errors
- [ ] Backend starts without errors
- [ ] Frontend builds without errors

#### Manual Verification
- [ ] Click "Add all to calendar" button - downloads .ics file
- [ ] Import .ics file into Apple Calendar - events appear correctly
- [ ] Import .ics file into Google Calendar - events appear correctly
- [ ] Event details (title, time, location) match original

**Implementation Note**: After completing Phase 3, pause for manual confirmation before proceeding.

---

## Phase 4: Polish and Configuration

### Overview

Connect the Week View to discovery results, clean up configuration, and improve error handling.

### Changes Required

#### 4.1 Share Events Between Discovery and Week View

**File**: `frontend/src/app/page.tsx`

Add state to share events:

```typescript
const [discoveredEvents, setDiscoveredEvents] = useState<CalendarEvent[]>([]);

const handleResultsReady = (events: CalendarEvent[]) => {
    console.log("Results ready:", events.length);
    setDiscoveredEvents(events);
};

const handleViewWeek = () => {
    // Store events in sessionStorage for week view
    sessionStorage.setItem("discoveredEvents", JSON.stringify(discoveredEvents));
    router.push("/week");
};
```

#### 4.2 Week View Uses Discovered Events

**File**: `frontend/src/app/week/page.tsx`

Replace mock data with sessionStorage + API:

```typescript
import { useEffect, useState } from "react";
import type { CalendarEvent } from "@/components/calendar";

export default function WeekPage() {
    const [weekStart, setWeekStart] = useState(() => getWeekStart(new Date()));
    const [events, setEvents] = useState<CalendarEvent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // First, check sessionStorage for discovered events
        const stored = sessionStorage.getItem("discoveredEvents");
        if (stored) {
            try {
                const parsed = JSON.parse(stored);
                // Convert date strings back to Date objects
                const events = parsed.map((e: any) => ({
                    ...e,
                    startTime: new Date(e.startTime),
                    endTime: e.endTime ? new Date(e.endTime) : undefined,
                }));
                setEvents(events);
            } catch (e) {
                console.error("Failed to parse stored events", e);
            }
        }
        setLoading(false);
    }, []);

    // Rest of component...

    if (loading) {
        return <div className="p-8 text-center">Loading...</div>;
    }

    return (
        <div className="min-h-screen px-6 py-8 md:px-12">
            {/* ... navigation ... */}

            {events.length === 0 ? (
                <div className="text-center py-12">
                    <p className="text-text-secondary">
                        No events yet. Start a search from the home page!
                    </p>
                </div>
            ) : (
                <WeekView
                    events={events}
                    weekStart={weekStart}
                    onEventClick={handleEventClick}
                    onEventHover={handleEventHover}
                />
            )}
        </div>
    );
}
```

#### 4.3 Create .env.example

**File**: `.env.example` (new file)

```bash
# ===========================================
# Calendar Club Environment Configuration
# ===========================================

# OpenAI API (Required)
# Get your key at https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_api_key

# Eventbrite API (Required for real events)
# Get your key at https://www.eventbrite.com/platform/api-keys
EVENTBRITE_API_KEY=your_eventbrite_api_key

# HyperDX Telemetry (Optional)
# For local development, use these values:
NEXT_PUBLIC_HYPERDX_API_KEY=local
NEXT_PUBLIC_HYPERDX_ENDPOINT=http://localhost:4318

# For production, get your key at https://www.hyperdx.io
# NEXT_PUBLIC_HYPERDX_API_KEY=your_hyperdx_api_key
```

#### 4.4 Add Error Toast Component

**File**: `frontend/src/components/ui/Toast.tsx` (new file)

```typescript
"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToastProps {
    message: string;
    type: "error" | "success" | "info";
    onClose: () => void;
    duration?: number;
}

export function Toast({ message, type, onClose, duration = 5000 }: ToastProps) {
    useEffect(() => {
        const timer = setTimeout(onClose, duration);
        return () => clearTimeout(timer);
    }, [duration, onClose]);

    const bgColor = {
        error: "bg-red-100 border-red-500 text-red-800",
        success: "bg-green-100 border-brand-green text-green-800",
        info: "bg-blue-100 border-blue-500 text-blue-800",
    }[type];

    return (
        <div
            className={cn(
                "fixed bottom-4 right-4 flex items-center gap-3 rounded-lg border-l-4 px-4 py-3 shadow-lg",
                bgColor
            )}
        >
            <p className="text-sm font-medium">{message}</p>
            <button onClick={onClose} className="hover:opacity-70">
                <X className="h-4 w-4" />
            </button>
        </div>
    );
}
```

#### 4.5 Update CORS for Production

**File**: `backend/main.py`

Use environment variable for origins:

```python
import os

# Get allowed origins from environment
ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Success Criteria

#### Automated Verification
- [ ] Backend starts: `uv run uvicorn backend.main:app --reload`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] `.env.example` exists with all required variables documented

#### Manual Verification
- [ ] Discover events → Click "View full week" → Events appear in week view
- [ ] Week view shows empty state when no events discovered
- [ ] Error messages display nicely (not raw error text)
- [ ] CORS works correctly (no console errors)

---

## Testing Strategy

### Unit Tests

**Backend** (`backend/tests/`):
- `test_eventbrite.py` - Mock Eventbrite API responses
- `test_calendar.py` - ICS generation validation
- `test_search_agent.py` - Profile to query transformation

**Frontend** (`frontend/src/__tests__/`):
- `api.test.ts` - API client error handling
- `DiscoveryChat.test.tsx` - Stream parsing

### Integration Tests

- Full flow: Query → Agent → Eventbrite → Results → Week View
- Calendar export: Event → ICS → Import verification

### Manual Testing Steps

1. Start fresh session (clear localStorage)
2. Type "AI meetups this weekend in Columbus"
3. Answer clarifying questions
4. Verify events are from Eventbrite (check URLs)
5. Click "Add all to calendar" - verify download
6. Click "View full week" - verify events transfer
7. Import .ics into calendar app - verify correctness

## Performance Considerations

- **Eventbrite API calls**: Cache responses for 5 minutes to reduce API usage
- **Large event lists**: Paginate results (show 10 at a time)
- **ICS generation**: Generate client-side if possible to reduce server load

## Migration Notes

No database migrations needed - all data flows through external APIs.

## References

- Production readiness research: `throughts/research/2026-01-09-production-readiness-gaps.md`
- Event API research: `throughts/research/Key Event API Sources and Their Limits.md`
- Calendar export research: `throughts/research/2025-01-09-calendar-export-integration.md`
- Eventbrite API docs: https://www.eventbrite.com/platform/docs/
