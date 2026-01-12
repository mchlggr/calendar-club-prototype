---
date: 2026-01-09T11:17:37-0500
researcher: Claude
git_commit: a3f0bc9c18b747c311fc1cdb7f6d2f09fac4d5d8
branch: main
repository: The-AI-Engineer-Challenge
topic: "Phase 0 UX Specification: Week View + Discovery Chat"
tags: [research, ux-spec, phase0, week-view, discovery-agent, design-system]
status: complete
last_updated: 2026-01-09
last_updated_by: Claude
---

# Phase 0 UX Specification: Week View + Discovery Chat

**Date**: 2026-01-09T11:17:37-0500
**Researcher**: Claude
**Git Commit**: a3f0bc9c18b747c311fc1cdb7f6d2f09fac4d5d8
**Branch**: main
**Repository**: The-AI-Engineer-Challenge

---

## Research Question

Design the initial chat prompt page/component in the same visual style as the provided week view design, and document both as implementable UX specs for MVP.

---

## Summary

This document extracts a design system from the Calendar Club week view mockup, defines the Week View UX spec (per DOC-11 requirements), and proposes a complementary Discovery Chat component that maintains visual consistency. Both components are designed for implementation with Next.js 14 + Tailwind CSS + shadcn/ui per the tech stack.

---

## Part 1: Design System (Extracted from Week View Mockup)

### Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `brand-green` | `#2D6A4F` (approx) | Logo, primary CTAs |
| `accent-orange` | `#E76F51` (approx) | Weekend dates, MEETUP tags, highlights |
| `accent-yellow` | `#F4D35E` (approx) | Highlight boxes, callouts |
| `accent-teal` | `#2A9D8F` (approx) | Secondary category tags |
| `accent-blue` | `#457B9D` (approx) | Tertiary category tags |
| `text-primary` | `#1D3557` (approx) | Headings, event titles |
| `text-secondary` | `#6B7280` | Times, metadata |
| `bg-cream` | `#FDFBF7` (approx) | Page background |
| `bg-white` | `#FFFFFF` | Cards, inputs |
| `border-light` | `#E5E7EB` | Grid lines, card borders |
| `grid-dots` | `#D1D5DB` | Notebook grid pattern |

### Typography

| Element | Style |
|---------|-------|
| **Hero headline (accent)** | Serif italic, ~48px, `brand-green` ("Tune into") |
| **Hero headline (emphasis)** | Sans-serif bold, ~48px, `text-primary` ("the signal.") |
| **Tagline** | Monospace/typewriter, ~14px, uppercase tracking, `text-primary` |
| **Day headers** | Sans-serif medium, ~12px, uppercase, `text-secondary` |
| **Date numbers** | Sans-serif semibold, ~20px |
| **Event time** | Sans-serif regular, ~11px, uppercase, `text-secondary` |
| **Event title** | Sans-serif medium, ~13px, `text-primary` |
| **Button text** | Sans-serif medium, ~14px, uppercase tracking |

### Spacing & Layout

| Token | Value |
|-------|-------|
| `page-padding` | 24px (mobile), 48px (desktop) |
| `section-gap` | 32px |
| `card-radius` | 8px |
| `input-radius` | 4px |
| `grid-gap` | 1px (border-based) |
| `event-gap` | 8px (vertical between events) |
| `event-padding` | 8px 12px |

### Visual Motifs

1. **Notebook Grid**: Subtle dotted/lined background giving planner aesthetic
2. **Tape Accents**: "Starts Here!" badge uses tape/sticker aesthetic with slight rotation
3. **Highlight Boxes**: Yellow background with subtle shadow for callouts
4. **Category Tags**: Small colored bars (2-4px) on event cards indicating type
5. **Soft Shadows**: `shadow-sm` on cards, inputs

---

## Part 2: Week View UX Spec (MVP)

### Component: `<WeekView />`

**Location**: `frontend/components/calendar/WeekView.tsx`

#### Visual Requirements (Must Ship)

| Requirement | Implementation | Priority |
|-------------|----------------|----------|
| **Weekend shading** | `bg-cream` on Sat/Sun columns vs `bg-white` on weekdays | P0 |
| **Today prominence** | Orange dot in header + `ring-1 ring-accent-orange` on column | P0 |
| **Date styling** | Weekend dates in `accent-orange`, weekday in `text-primary` | P0 |
| **Event cards** | White background, `border-light`, `shadow-sm`, 8px radius | P0 |
| **Category color** | 2-4px left border color per category (orange/green/blue) | P0 |
| **Time display** | Uppercase, 11px, `text-secondary` above title | P0 |
| **Density indication** | When 3+ events, show faint `accent-yellow/20` band | P1 |
| **Now marker** | Hairline at current time (if viewing today's week) | P1 |

#### Interaction Requirements (Must Ship)

| Interaction | Behavior | Priority |
|-------------|----------|----------|
| **Hover peek** | Card lifts slightly, shows peek tooltip with location + RSVP link | P0 |
| **Click to expand** | Opens event detail modal or navigates to event page | P0 |
| **Week navigation** | Arrow buttons or swipe to move between weeks | P0 |
| **Keyboard nav** | Arrow keys move focus between events, Enter to select | P1 |

#### Data Shape

```typescript
interface CalendarEvent {
  id: string;
  title: string;
  startTime: Date;
  endTime: Date;
  category: 'meetup' | 'startup' | 'community' | 'ai';
  venue?: string;
  neighborhood?: string;
  canonicalUrl: string;
  sourceId: string;
}

interface WeekViewProps {
  events: CalendarEvent[];
  weekStart: Date; // Sunday
  onEventClick: (event: CalendarEvent) => void;
  onEventHover?: (event: CalendarEvent | null) => void;
  focusedDay?: Date;
}
```

#### Instrumentation Events

```typescript
// Emit on initial render
{ event: 'results_viewed', count: number, latencyMs: number }

// Emit on event click
{ event: 'event_clicked_out', eventId: string, source: string, category: string }

// Emit on hover (debounced 300ms)
{ event: 'calendar:event_hover', eventId: string, dayOfWeek: number }
```

---

## Part 3: Discovery Chat UX Spec (MVP)

### Component: `<DiscoveryChat />`

**Location**: `frontend/components/discovery/DiscoveryChat.tsx`

The Discovery Chat is the entry point to the "deep research agent" experience. It maintains the same warm, editorial aesthetic as the Week View.

### Visual Design

#### Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  [Calendar Club Logo]                    [LOGIN | SUBSCRIBE] │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ● Tune into                                                │
│     the signal.                                              │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │ "A curated directory of the best technical meetups.  │  │
│   │  No noise, just deep cuts."                          │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │  💬 What are you looking for?                        │  │
│   │                                                      │  │
│   │  ┌──────────────────────────────────────────────┐   │  │
│   │  │ Find AI meetups this weekend...              │   │  │
│   │  └──────────────────────────────────────────────┘   │  │
│   │                                                      │  │
│   │  Quick picks:                                        │  │
│   │  [This weekend] [AI/Tech] [Startups] [Free events]   │  │
│   │                                                      │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │  [Notebook grid background]                          │  │
│   │                                                      │  │
│   │  Recent searches:                                    │  │
│   │  • "startup events next Thursday"                    │  │
│   │  • "community meetups downtown"                      │  │
│   │                                                      │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### Visual Specifications

| Element | Style |
|---------|-------|
| **Chat card** | White bg, `border-light`, `shadow-md`, 12px radius |
| **Input field** | Full width, 16px padding, `border-light`, 4px radius, placeholder in `text-secondary` |
| **Quick pick chips** | `bg-cream` default, `bg-accent-yellow` on hover, 16px radius, 8px 16px padding |
| **Section headers** | Sans-serif medium, 12px, uppercase tracking, `text-secondary` |
| **Recent searches** | List with bullet, `text-primary`, hover underline |

#### Chat Flow States

**State 1: Initial Prompt**
- Show hero + tagline
- Large input field with placeholder "Find AI meetups this weekend..."
- Quick pick chips for common intents
- Recent searches (from localStorage)

**State 2: Clarifying Questions**
- Agent asks 2-4 clarifying questions
- Questions appear as chat bubbles (agent style)
- User responds via chips or text input
- Visual: Agent bubble has `brand-green` left border, user bubble has `accent-orange` left border

**State 3: Processing**
- Skeleton loading in chat
- "Searching through 847 events..." animated text
- Notebook grid background visible

**State 4: Results Preview**
- Agent says "I found 12 events that match..."
- Shows 3-5 preview cards inline
- "View full week" CTA button
- Option to refine: "Want me to narrow it down?"

**State 5: Week View Transition**
- Smooth transition/navigation to WeekView
- Filters preserved from chat

### Clarifying Questions Rubric

The agent asks up to 4 questions based on missing information:

| Missing Info | Question | UI |
|--------------|----------|-----|
| **Time window** | "When are you looking?" | Chips: [Today] [This weekend] [Next week] [Pick dates] |
| **Category** | "What kind of events?" | Chips: [AI/Tech] [Startups] [Community] [All of the above] |
| **Location** | "How far will you go?" | Chips: [Downtown only] [Within 15 min] [Anywhere in Columbus] |
| **Cost** | "Free, paid, or both?" | Chips: [Free only] [Any price] |

After 2-3 quick picks, the agent proceeds with search. User can always type free-form instead.

### Data Shape

```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
  chips?: ChipOption[]; // For clarifying questions
}

interface ChipOption {
  label: string;
  value: string;
  selected?: boolean;
}

interface DiscoveryChatProps {
  onSearch: (query: SearchQuery) => void;
  onResultsReady: (events: CalendarEvent[]) => void;
  initialQuery?: string;
}

interface SearchQuery {
  rawText: string;
  parsedIntent: {
    timeWindow?: { start: Date; end: Date };
    categories?: string[];
    maxDistance?: number;
    freeOnly?: boolean;
  };
}
```

### Instrumentation Events

```typescript
// Emit when search submitted
{ event: 'search_performed', query: string, parsedIntent: object, chips_used: string[] }

// Emit when clarifying question answered
{ event: 'clarification_answered', question_type: string, answer: string, method: 'chip' | 'text' }

// Emit when results shown
{ event: 'results_viewed', count: number, latencyMs: number, from: 'chat' }

// Emit when user clicks event from chat preview
{ event: 'event_clicked_out', eventId: string, source: 'chat_preview' }
```

---

## Part 4: Component Architecture

### File Structure (aligned with TECHSTACK.md)

```
frontend/
├── app/
│   ├── page.tsx              # Discovery home (DiscoveryChat)
│   ├── week/
│   │   └── page.tsx          # Week view page
│   └── share/
│       └── [id]/
│           └── page.tsx      # Shareable calendar links
├── components/
│   ├── calendar/
│   │   ├── WeekView.tsx      # Main week grid
│   │   ├── DayColumn.tsx     # Single day column
│   │   ├── EventCard.tsx     # Event card with category color
│   │   ├── WeekHeader.tsx    # Sun-Sat headers with dates
│   │   ├── NowMarker.tsx     # Current time indicator
│   │   └── EventPeek.tsx     # Hover preview tooltip
│   ├── discovery/
│   │   ├── DiscoveryChat.tsx # Main chat interface
│   │   ├── ChatInput.tsx     # Text input with placeholder
│   │   ├── ChatMessage.tsx   # Single message bubble
│   │   ├── QuickPicks.tsx    # Chip selection row
│   │   ├── ResultsPreview.tsx# Inline event preview cards
│   │   └── ClarifyingQ.tsx   # Clarifying question with chips
│   ├── layout/
│   │   ├── Header.tsx        # Logo + Login/Subscribe
│   │   ├── Hero.tsx          # "Tune into the signal"
│   │   └── HighlightBox.tsx  # Yellow callout box
│   └── ui/                   # shadcn/ui components
│       ├── button.tsx
│       ├── input.tsx
│       ├── card.tsx
│       └── chip.tsx          # Custom chip component
├── lib/
│   ├── telemetry.ts          # HyperDX + session UUID
│   └── api.ts                # API client for backend
└── styles/
    └── globals.css           # Tailwind + custom tokens
```

### Tailwind Configuration

```typescript
// tailwind.config.ts (extend)
{
  theme: {
    extend: {
      colors: {
        brand: {
          green: '#2D6A4F',
        },
        accent: {
          orange: '#E76F51',
          yellow: '#F4D35E',
          teal: '#2A9D8F',
          blue: '#457B9D',
        },
        cream: '#FDFBF7',
      },
      fontFamily: {
        serif: ['Georgia', 'Times New Roman', 'serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      backgroundImage: {
        'notebook-grid': 'radial-gradient(circle, #D1D5DB 1px, transparent 1px)',
      },
      backgroundSize: {
        'notebook': '20px 20px',
      },
    },
  },
}
```

---

## Part 5: MVP Acceptance Criteria

### Week View

- [ ] 7-day grid renders with correct date headers
- [ ] Weekend columns have `bg-cream` shading
- [ ] Today column has visual prominence (ring + dot)
- [ ] Events display with time, title, and category color
- [ ] Clicking event triggers `event_clicked_out` and opens canonical URL
- [ ] Week navigation works (prev/next buttons)
- [ ] Mobile responsive (horizontal scroll or day-at-a-time)

### Discovery Chat

- [ ] Input accepts free-form text queries
- [ ] Quick pick chips are clickable and update input
- [ ] Agent asks clarifying questions when intent is ambiguous
- [ ] Results preview shows 3-5 events inline
- [ ] "View full week" navigates to WeekView with filters
- [ ] `search_performed` event fires on submit
- [ ] Session UUID persists in localStorage

### Quality Bar (from ROADMAP.md)

- [ ] Week view loads in <2s on 3G connection
- [ ] Results include time, location, and canonical link
- [ ] Duplicate events are rare in top results (<5% dup rate)
- [ ] Search → Results latency <3s (excluding LLM cold start)

---

## Code References

- Design requirements: `throughts/research/Designing a Human Week‑View Calendar.md`
- Tech stack: `TECHSTACK.md:49-74` (Next.js 14 + Tailwind + shadcn/ui)
- Instrumentation: `TECHSTACK.md:259-264` (telemetry events)
- User flows: `ROADMAP.md:61-71` (minimum user journeys)

---

## Open Questions

1. **Font licensing**: The mockup appears to use a specific serif font for "Tune into" - need to identify and confirm licensing (Georgia is a safe fallback)
2. **All-day events**: The mockup doesn't show all-day events - should we include the "all-day strip" from DOC-11 in MVP?
3. **Mobile UX**: Horizontal scroll for week, or day-at-a-time view? (Recommend day-at-a-time for MVP)
4. **Animation budget**: The tape/sticker aesthetic suggests playful motion - how much animation is acceptable for MVP?
