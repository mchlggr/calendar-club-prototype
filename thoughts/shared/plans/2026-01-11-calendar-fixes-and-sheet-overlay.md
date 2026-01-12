# Calendar Fixes and Sheet Overlay Implementation Plan

## Overview

This plan addresses three related improvements to the calendar system:
1. **Backend date handling** - Fix scraped events defaulting to `datetime.now()` when dates are missing
2. **Calendar styling** - Show grid pattern on all days, highlight only current day
3. **Sheet overlay** - Convert calendar to a URL-based modal using Next.js parallel routes

## Current State Analysis

### Backend Date Issue
- Scraped events (Posh, Luma, Partiful, Meetup scraper) default to `datetime.now()` when `start_time` is `None`
- API sources (Eventbrite) exclude events without dates
- This inconsistency causes events with unparseable dates to appear on "today"

### Calendar Styling Issue
- Grid pattern (`bg-grid-paper`) is on parent container
- Weekend columns use `weekend-column` class with solid background that covers the grid
- Both weekends AND today get special highlighting

### Current Routing
- Next.js 16.1.1 with App Router
- Single `layout.tsx` at app level
- `/week` is a separate page route
- Events stored in sessionStorage for state transfer

## Desired End State

1. **Events with missing dates are excluded** from results (consistent with API sources)
2. **All calendar days show the grid pattern**, weekends are dimmed with opacity
3. **Only the current day is highlighted** with an outline
4. **Calendar opens as a sheet** sliding up from bottom with blurred backdrop
5. **URL updates to `/week`** when calendar opens, state is preserved when closed

### Verification:
- Search for events → all results have real dates (not today's date)
- Calendar view shows grid on all 7 days
- Only current day has highlight styling
- Clicking "View Week" shows smooth slide-up animation with blur
- Browser back closes the sheet and returns to homepage

## What We're NOT Doing

- Improving date parsing in individual extractors (future work)
- Adding time-based vertical positioning for events
- Multi-week navigation in sheet mode (works in full page mode)
- Touch gesture support for dragging sheet closed

## Implementation Approach

We'll implement in three phases, with each phase independently deployable:

1. **Phase 1**: Backend date fix (excludes events without dates)
2. **Phase 2**: Calendar styling (grid on all days, today-only highlight)
3. **Phase 3**: Sheet overlay with parallel routes

---

## Phase 1: Backend Date Handling Fix

### Overview
Exclude scraped events without dates instead of defaulting to current time. Add logging to identify which sources are returning events without dates.

### Changes Required:

#### 1.1 Update Scraped Event Converter

**File**: `api/agents/search.py`
**Changes**: Return `None` for events without dates, add logging

```python
# Around line 128-151 - Replace _convert_scraped_event function

def _convert_scraped_event(event: ScrapedEvent) -> EventResult | None:
    """Convert scraped event to EventResult. Returns None if date is missing."""
    # Skip events without dates
    if not event.start_time:
        logger.debug(
            "⏭️ [Search] Skipping event without date | source=%s title=%s url=%s",
            event.source,
            event.title[:50] if event.title else "untitled",
            event.url or "no-url",
        )
        return None

    # Build location string
    location = event.venue_name or "TBD"
    if event.venue_address:
        location = f"{location}, {event.venue_address}"

    return EventResult(
        id=f"posh-{event.event_id}",
        title=event.title,
        date=event.start_time.isoformat(),
        location=location,
        category=event.category,
        description=event.description[:200] if event.description else "",
        is_free=event.is_free,
        price_amount=event.price_amount,
        distance_miles=0.0,  # Will be calculated if needed
        url=event.url,
    )
```

#### 1.2 Update Exa Event Converter

**File**: `api/agents/search.py`
**Changes**: Return `None` for Exa events without published dates

```python
# Around line 96-126 - Replace _convert_exa_result function

def _convert_exa_result(result: ExaResult) -> EventResult | None:
    """Convert Exa search result to EventResult. Returns None if date is missing."""
    if not result.url:
        return None

    # Skip results without dates
    if not result.published_date:
        logger.debug(
            "⏭️ [Search] Skipping Exa result without date | title=%s url=%s",
            result.title[:50] if result.title else "untitled",
            result.url[:80],
        )
        return None

    event_id = hashlib.md5(result.url.encode()).hexdigest()[:12]
    date_str = result.published_date.isoformat()

    # Use highlights for description, fall back to text snippet
    description = ""
    if result.highlights:
        description = " ".join(result.highlights)[:200]
    elif result.text:
        description = result.text[:200]

    return EventResult(
        id=f"exa-{event_id}",
        title=result.title or "Untitled Event",
        date=date_str,
        location="See event page",
        category="community",
        description=description,
        is_free=True,
        price_amount=None,
        distance_miles=0.0,
        url=result.url,
    )
```

#### 1.3 Update Result Conversion to Handle None

**File**: `api/agents/search.py`
**Changes**: Filter out `None` results from conversion

```python
# Around line 319-356 - In _convert_source_results, ensure None values are filtered

# After the for loop that calls converters, filter None values:
# Change:
#     all_events.extend(converted)
# To:
#     all_events.extend([e for e in converted if e is not None])
```

### Success Criteria:

#### Automated Verification:
- [x] API server starts without errors: `cd api && uv run python -c "from agents.search import search_events; print('OK')"`
- [x] Type checking passes: `cd api && uv run pyright`
- [x] Existing tests pass: `cd api && uv run pytest agents/tests/test_search.py -v`

#### Manual Verification:
- [ ] Search for events → check server logs for "Skipping event without date" messages
- [ ] Events that appear in results all have real dates (not today's date clustered)
- [ ] Calendar view shows events distributed across multiple days

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the date distribution is working correctly before proceeding to Phase 2.

---

## Phase 2: Calendar Styling Fixes

### Overview
Update calendar styling so grid pattern shows on all days, weekends are dimmed with opacity, and only the current day gets a highlight.

### Changes Required:

#### 2.1 Update DayColumn Component

**File**: `frontend/src/components/calendar/DayColumn.tsx`
**Changes**: Remove solid weekend background, add opacity-based dimming

```tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DayColumnProps {
	date: Date;
	isWeekend: boolean;
	isToday: boolean;
	eventCount?: number;
	children?: ReactNode;
	className?: string;
}

export function DayColumn({
	date,
	isWeekend,
	isToday,
	eventCount = 0,
	children,
	className,
}: DayColumnProps) {
	const hasHighDensity = eventCount >= 3;

	return (
		<div
			className={cn(
				"flex min-h-[220px] flex-col gap-2 border-r-2 border-text-primary p-3 last:border-r-0",
				// Grid shows through on all days (no solid backgrounds)
				isWeekend && "weekend-dim",
				isToday && "today-highlight",
				hasHighDensity && "density-high",
				className,
			)}
			data-date={date.toISOString().split("T")[0]}
		>
			{children}
		</div>
	);
}
```

#### 2.2 Update WeekHeader Component

**File**: `frontend/src/components/calendar/WeekHeader.tsx`
**Changes**: Apply consistent weekend dimming, keep today indicator

Find and update the day cell styling (around line 47):

```tsx
// Change weekend styling from solid background to opacity-based
<div
	key={date.toISOString()}
	className={cn(
		"flex flex-col items-center border-r-2 border-text-primary py-3 last:border-r-0",
		isWeekend && "weekend-dim",
	)}
>
```

Also update the date number styling (around line 61):

```tsx
<span
	className={cn(
		"cc-date-number",
		isToday ? "text-accent-orange" : "text-text-primary",
		// Remove weekend-specific orange text
	)}
>
	{date.getDate()}
</span>
```

#### 2.3 Update CSS Classes

**File**: `frontend/src/styles/globals.css`
**Changes**: Replace solid backgrounds with opacity-based styling

```css
/* Around line 579-592 - Replace calendar day column states */

/* Calendar day column states */
.weekend-dim {
  /* Dim weekends but allow grid to show through */
  opacity: 0.6;
}

.today-highlight {
  /* Highlight current day with outline only (no solid background) */
  outline: 2px solid var(--color-accent-orange);
  outline-offset: -2px;
  opacity: 1; /* Override weekend dimming if today is a weekend */
}

.density-high {
  gap: 0.375rem;
}
```

Remove or comment out the old `.weekend-column` and `.today-column` classes.

### Success Criteria:

#### Automated Verification:
- [x] Frontend builds without errors: `cd frontend && npm run build`
- [x] Linting passes: `cd frontend && npm run lint`
- [x] No TypeScript errors: `cd frontend && npx tsc --noEmit`

#### Manual Verification:
- [ ] Grid pattern visible on ALL 7 days (including weekends)
- [ ] Weekend columns are visually dimmer (reduced opacity)
- [ ] Only current day has orange outline
- [ ] If today is a weekend, it has outline AND is not dimmed

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation that the styling looks correct before proceeding to Phase 3.

---

## Phase 3: Sheet Overlay with Parallel Routes

### Overview
Convert calendar to a URL-based sheet overlay using Next.js parallel routes. The calendar slides up from the bottom with a blurred backdrop when opened via the homepage.

### Changes Required:

#### 3.1 Install Framer Motion

**Command**:
```bash
cd frontend && npm install framer-motion
```

#### 3.2 Update Root Layout for Parallel Routes

**File**: `frontend/src/app/layout.tsx`
**Changes**: Accept `calendar` slot prop

```tsx
import type { Metadata } from "next";
import {
	Instrument_Serif,
	Inter,
	JetBrains_Mono,
	Permanent_Marker,
	Tilt_Warp,
} from "next/font/google";
import { Suspense } from "react";
import "@/styles/globals.css";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { PostHogProvider } from "@/components/PostHogProvider";
import { TelemetryProvider } from "@/components/TelemetryProvider";

const inter = Inter({
	variable: "--font-inter",
	subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
	variable: "--font-jetbrains",
	subsets: ["latin"],
});

const permanentMarker = Permanent_Marker({
	variable: "--font-marker",
	subsets: ["latin"],
	weight: "400",
});

const instrumentSerif = Instrument_Serif({
	variable: "--font-instrument",
	subsets: ["latin"],
	weight: "400",
	style: ["normal", "italic"],
});

const tiltWarp = Tilt_Warp({
	variable: "--font-tilt-warp",
	subsets: ["latin"],
});

export const metadata: Metadata = {
	title: "Calendar Club",
	description:
		"Discover in-person events and download a calendar file for your week.",
};

export default function RootLayout({
	children,
	calendar,
}: Readonly<{
	children: React.ReactNode;
	calendar: React.ReactNode;
}>) {
	return (
		<html lang="en">
			<body
				className={`${inter.variable} ${jetbrainsMono.variable} ${permanentMarker.variable} ${instrumentSerif.variable} ${tiltWarp.variable} min-h-screen bg-bg-cream font-sans antialiased`}
			>
				<Suspense fallback={null}>
					<PostHogProvider>
						<TelemetryProvider>
							<Header />
							<main>{children}</main>
							<Footer />
							{calendar}
						</TelemetryProvider>
					</PostHogProvider>
				</Suspense>
			</body>
		</html>
	);
}
```

#### 3.3 Create Default Slot

**File**: `frontend/src/app/@calendar/default.tsx` (NEW FILE)

```tsx
export default function Default() {
	return null;
}
```

#### 3.4 Create Intercepted Week Route

**File**: `frontend/src/app/@calendar/(.)week/page.tsx` (NEW FILE)

```tsx
"use client";

import { CalendarSheet } from "@/components/calendar/CalendarSheet";

export default function WeekModal() {
	return <CalendarSheet />;
}
```

#### 3.5 Create CalendarSheet Component

**File**: `frontend/src/components/calendar/CalendarSheet.tsx` (NEW FILE)

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { X, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { WeekView } from "./WeekView";
import type { CalendarEvent } from "./types";

function getWeekStart(date: Date): Date {
	const d = new Date(date);
	const day = d.getDay();
	d.setDate(d.getDate() - day);
	d.setHours(0, 0, 0, 0);
	return d;
}

export function CalendarSheet() {
	const router = useRouter();
	const [events, setEvents] = useState<CalendarEvent[]>([]);
	const [weekStart, setWeekStart] = useState(() => getWeekStart(new Date()));

	// Load events from sessionStorage
	useEffect(() => {
		const stored = sessionStorage.getItem("discoveredEvents");
		if (stored) {
			try {
				const parsed = JSON.parse(stored);
				const loadedEvents = parsed.map(
					(e: Record<string, unknown>): CalendarEvent => {
						const startTime = new Date(e.startTime as string);
						const endTime = e.endTime
							? new Date(e.endTime as string)
							: new Date(startTime.getTime() + 2 * 60 * 60 * 1000);
						return {
							...e,
							startTime,
							endTime,
						} as CalendarEvent;
					}
				);
				setEvents(loadedEvents);
			} catch (error) {
				console.error("Failed to parse stored events:", error);
			}
		}
	}, []);

	const handleClose = useCallback(() => {
		router.back();
	}, [router]);

	const handlePrevWeek = () => {
		const prev = new Date(weekStart);
		prev.setDate(prev.getDate() - 7);
		setWeekStart(prev);
	};

	const handleNextWeek = () => {
		const next = new Date(weekStart);
		next.setDate(next.getDate() + 7);
		setWeekStart(next);
	};

	const handleEventClick = (event: CalendarEvent) => {
		if (event.canonicalUrl) {
			window.open(event.canonicalUrl, "_blank");
		}
	};

	// Close on Escape key
	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.key === "Escape") handleClose();
		};
		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [handleClose]);

	return (
		<>
			{/* Backdrop */}
			<motion.div
				initial={{ opacity: 0 }}
				animate={{ opacity: 1 }}
				exit={{ opacity: 0 }}
				transition={{ duration: 0.2 }}
				className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
				onClick={handleClose}
			/>

			{/* Sheet */}
			<motion.div
				initial={{ y: "100%" }}
				animate={{ y: 0 }}
				exit={{ y: "100%" }}
				transition={{ type: "spring", damping: 30, stiffness: 300 }}
				className="fixed inset-x-0 bottom-0 z-50 flex h-[85vh] flex-col rounded-t-2xl bg-bg-cream shadow-2xl"
				onClick={(e) => e.stopPropagation()}
			>
				{/* Handle bar */}
				<div className="flex justify-center py-2">
					<div className="h-1.5 w-12 rounded-full bg-gray-300" />
				</div>

				{/* Header */}
				<div className="flex items-center justify-between border-b border-border-light px-4 pb-3">
					<div className="flex items-center gap-2">
						<button
							onClick={handlePrevWeek}
							className="rounded-full p-2 hover:bg-gray-100"
							aria-label="Previous week"
						>
							<ChevronLeft className="h-5 w-5" />
						</button>
						<button
							onClick={handleNextWeek}
							className="rounded-full p-2 hover:bg-gray-100"
							aria-label="Next week"
						>
							<ChevronRight className="h-5 w-5" />
						</button>
					</div>

					<div className="flex items-center gap-2">
						<button
							className="flex items-center gap-1 rounded-lg bg-brand-green px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-green/90"
						>
							<Download className="h-4 w-4" />
							Export .ics
						</button>
						<button
							onClick={handleClose}
							className="rounded-full p-2 hover:bg-gray-100"
							aria-label="Close"
						>
							<X className="h-5 w-5" />
						</button>
					</div>
				</div>

				{/* Calendar content */}
				<div className="flex-1 overflow-y-auto p-4">
					<WeekView
						events={events}
						weekStart={weekStart}
						onEventClick={handleEventClick}
					/>
				</div>
			</motion.div>
		</>
	);
}
```

#### 3.6 Update Homepage Navigation

**File**: `frontend/src/app/page.tsx`
**Changes**: Use Link for navigation instead of router.push

```tsx
// Replace the handleViewWeek function and button with:

// Import at top:
import Link from "next/link";

// In the component, store events before navigation:
const prepareViewWeek = () => {
	if (discoveredEvents.length > 0) {
		sessionStorage.setItem(
			"discoveredEvents",
			JSON.stringify(discoveredEvents),
		);
	}
};

// Replace the button with:
<Link
	href="/week"
	onClick={prepareViewWeek}
	className="... existing button styles ..."
>
	View Week
</Link>
```

#### 3.7 Update Existing Week Page (Full Page Fallback)

**File**: `frontend/src/app/week/page.tsx`
**Changes**: Keep as-is for direct navigation fallback. The page works correctly when accessed directly.

#### 3.8 Update Calendar Index Exports

**File**: `frontend/src/components/calendar/index.ts`
**Changes**: Export the new CalendarSheet component

```tsx
export { DayColumn } from "./DayColumn";
export { EventCard } from "./EventCard";
export { EventPeek } from "./EventPeek";
export { WeekHeader } from "./WeekHeader";
export { WeekView } from "./WeekView";
export { CalendarSheet } from "./CalendarSheet";
export type { CalendarEvent, EventCategory } from "./types";
```

### Success Criteria:

#### Automated Verification:
- [x] Dependencies install: `cd frontend && npm install`
- [x] Frontend builds without errors: `cd frontend && npm run build`
- [x] Linting passes: `cd frontend && npm run lint`
- [x] No TypeScript errors: `cd frontend && npx tsc --noEmit`

#### Manual Verification:
- [ ] From homepage, click "View Week" → sheet slides up from bottom
- [ ] Backdrop blurs and dims the homepage
- [ ] URL changes to `/week`
- [ ] Press Escape or click backdrop → sheet closes, URL returns to `/`
- [ ] Browser back button closes sheet
- [ ] Direct navigation to `/week` shows full page (no sheet)
- [ ] Page refresh while sheet is open shows full page calendar
- [ ] Week navigation (prev/next) works in sheet mode
- [ ] Events are correctly displayed

**Implementation Note**: After completing this phase and all verification passes, the full implementation is complete.

---

## Testing Strategy

### Unit Tests:
- Test `_convert_scraped_event` returns `None` for events without `start_time`
- Test `_convert_exa_result` returns `None` for results without `published_date`

### Integration Tests:
- End-to-end search flow returns only events with valid dates
- Calendar sheet opens and closes correctly

### Manual Testing Steps:
1. Perform a search, verify no events appear on "today" unless they actually occur today
2. Open week view, verify grid pattern on all days
3. Verify only current day has highlight
4. Test sheet open/close via click, Escape key, and browser back
5. Test direct navigation to `/week` shows full page

## Performance Considerations

- Framer Motion adds ~50KB to bundle (acceptable for animation quality)
- Sheet content lazy-loads from sessionStorage
- No additional API calls when opening sheet

## Migration Notes

- No database changes required
- No backwards compatibility concerns
- Users on old cached pages will see full page on refresh (expected behavior)

## References

- Research document: `thoughts/shared/research/2026-01-11-calendar-sheet-nextjs-parallel-routes.md`
- Backend date analysis: `thoughts/shared/research/2026-01-11-calendar-event-distribution-and-styling.md`
- Next.js Parallel Routes: https://nextjs.org/docs/app/api-reference/file-conventions/parallel-routes
