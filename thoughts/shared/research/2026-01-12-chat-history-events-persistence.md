---
date: 2026-01-12T05:37:30Z
researcher: Claude
git_commit: f6f76a42e1dbc741d8b0d168352e5020b2161069
branch: main
repository: calendar-club-prototype
topic: "Chat History Event Display Persistence"
tags: [research, codebase, chat, events, state-management, frontend]
status: complete
last_updated: 2026-01-12
last_updated_by: Claude
---

# Research: Chat History Event Display Persistence

**Date**: 2026-01-12T05:37:30Z
**Researcher**: Claude
**Git Commit**: f6f76a42e1dbc741d8b0d168352e5020b2161069
**Branch**: main
**Repository**: calendar-club-prototype

## Research Question

Why do events recommended by the assistant not persist in chat history? When viewing the chat, only the most recent assistant response shows event cards, while earlier responses that mentioned events show only the text message without the corresponding event cards.

## Summary

**Root Architecture**: Messages and events are stored in completely separate state buckets. The `messages` array contains only text content, while `pendingResults` is a single global state that holds the current event results. When a new search happens, `pendingResults` is **replaced**, not accumulated. This causes older assistant responses to lose their associated events.

**Key finding**: The `ChatMessage` interface has no `events` field - it only contains `id`, `role`, and `content`. Events are rendered once at the bottom of the chat via `ResultsPreview`, not inline with each message that generated them.

## Detailed Findings

### 1. Message Data Structure

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx:36-40`

```typescript
interface ChatMessage {
  id: string;
  role: "user" | "agent"I'm not worried about persisting the events to a back-end session right now for recovery. Don't worry about that. I think the simplest thing is to embed them in the chat messages on the front-end when it's received. We'll probably want to refactor that later because it is a decision that's very particular and specific to this chat experience and that might evolve. But for now I think it's okay to do approach A ;
  content: string;
}
```

The message type is purely conversational text with no `events` field. There is no mechanism to associate events with the message that generated them.

### 2. State Architecture

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx:85-99`

The component maintains three separate state buckets:

| State | Type | Purpose | Lifecycle |
|-------|------|---------|-----------|
| `messages` | `ChatMessage[]` | Completed chat messages | Accumulates across queries |
| `pendingResults` | `CalendarEvent[]` | Events from API | **Replaced** on each search |
| `streamingMessage` | `string` | Current streaming response | Cleared on completion |

**Critical detail**: Events and messages flow through completely independent channels.

### 3. Event Replacement Behavior

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx:131-155`

When events arrive from the SSE stream:

```typescript
else if (event.type === "events" && event.events) {
  const mappedEvents = event.events.map(mapApiEventToCalendarEvent);
  setPendingResults(mappedEvents);  // REPLACES, not appends
  onResultsReady(mappedEvents);
}
```

Line 154: `setPendingResults(mappedEvents)` completely replaces the previous results. This is why only the most recent search results are visible.

### 4. Message Rendering

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx:310-322`

Historical messages are rendered without any event association:

```jsx
{messages.map((message) => (
  <div key={message.id} className={...}>
    <p className="text-sm">{message.content}</p>
  </div>
))}
```

Only `message.content` (text) is rendered. No event data is accessed here.

### 5. Results Display

**File**: `frontend/src/components/discovery/DiscoveryChat.tsx:363-369`

Events are rendered as a single block at the end, not associated with specific messages:

```jsx
{showResults && (
  <ResultsPreview
    events={pendingResults}
    totalCount={pendingResults.length}
    onViewWeek={onViewWeek}
  />
)}
```

The display condition (`showResults`) is:
```typescript
const showResults = !isProcessing && pendingResults.length > 0;
```

### 6. Data Flow Diagram

```
User Query #1
  └─ "events" SSE event arrives
       └─ setPendingResults(events1)  // pendingResults = events1
       └─ setMessages([...msgs, agentMsg1])
       └─ ResultsPreview shows events1 ✓

User Query #2
  └─ "events" SSE event arrives
       └─ setPendingResults(events2)  // pendingResults = events2 (REPLACED!)
       └─ setMessages([...msgs, agentMsg2])
       └─ ResultsPreview shows events2 ✓
       └─ agentMsg1 shows text only, events1 LOST ✗
```

## Code References

| Location | Description |
|----------|-------------|
| `frontend/src/components/discovery/DiscoveryChat.tsx:36-40` | ChatMessage interface definition |
| `frontend/src/components/discovery/DiscoveryChat.tsx:85-99` | State declarations |
| `frontend/src/components/discovery/DiscoveryChat.tsx:131-155` | Event stream handling |
| `frontend/src/components/discovery/DiscoveryChat.tsx:310-322` | Message rendering loop |
| `frontend/src/components/discovery/DiscoveryChat.tsx:363-369` | ResultsPreview rendering |
| `frontend/src/components/discovery/ResultsPreview.tsx:44` | ResultsPreview component |
| `frontend/src/lib/api.ts:32-35` | Wire ChatMessage type |
| `frontend/src/lib/api.ts:48-72` | ChatStreamEvent types |

## Architecture Documentation

### Current Pattern

1. **Flat message storage**: Messages stored as simple text objects
2. **Global event state**: Single `pendingResults` state for all events
3. **Replacement semantics**: New events replace old events entirely
4. **Decoupled rendering**: Events rendered separately from messages

### Wire Protocol

Events arrive via SSE with type `"events"` or `"more_events"`:

```typescript
// api.ts ChatStreamEvent
{
  type: "events" | "more_events";
  events?: DiscoveryEventWire[];
}
```

The `"more_events"` type does merge (dedupe by ID), but `"events"` replaces.

### Session Persistence

Backend uses SQLite via OpenAI Agents SDK's `SQLiteSession` for conversation history. However, this stores conversation turns, not event results. Events are ephemeral to the streaming session.

## Implementation Guidance for Developer

To preserve events in chat history, the developer should consider:

### Approach A: Embed Events in Messages

1. Extend `ChatMessage` interface:
   ```typescript
   interface ChatMessage {
     id: string;
     role: "user" | "agent";
     content: string;
     events?: CalendarEvent[];  // NEW
   }
   ```

2. When `"done"` event fires, capture `pendingResults` with the message:
   ```typescript
   setMessages((msgs) => [
     ...msgs,
     {
       id: crypto.randomUUID(),
       role: "agent",
       content: finalMessage,
       events: pendingResultsRef.current, // Capture current events
     },
   ]);
   ```

3. Update message rendering to show inline events:
   ```jsx
   {messages.map((message) => (
     <div key={message.id}>
       <p>{message.content}</p>
       {message.events?.length > 0 && (
         <ResultsPreview events={message.events} ... />
       )}
     </div>
   ))}
   ```

### Approach B: Event History by Turn

1. Create `eventsByTurn` state: `Map<string, CalendarEvent[]>`
2. Key events by message ID when stream completes
3. Look up events by message ID during rendering

### Key Files to Modify

| File | Changes Needed |
|------|----------------|
| `frontend/src/components/discovery/DiscoveryChat.tsx` | State structure, event capture on "done", rendering |
| `frontend/src/components/discovery/ResultsPreview.tsx` | May need variant for inline display |
| `frontend/src/lib/api.ts` | Update ChatMessage type if using Approach A |

### Testing Considerations

1. Send multiple queries in one session
2. Verify each message shows its associated events
3. Verify new queries don't affect previous message events
4. Test "no results" case (should show empty, not previous events)

## Related Research

- `thoughts/shared/research/2026-01-11-events-not-rendering-ui.md` - Related UI event rendering issue
- `thoughts/shared/research/2026-01-11-agentic-flow-search-architecture.md` - Search architecture context

## Open Questions

1. Should events be persisted to backend session storage for cross-session recovery?
2. Should there be a maximum number of historical event displays for performance?
3. Should "more_events" from background search update historical messages or only current?
