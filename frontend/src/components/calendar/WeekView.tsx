"use client";

import { useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import { DayColumn } from "./DayColumn";
import { EventCard } from "./EventCard";
import { EventPeek } from "./EventPeek";
import type { CalendarEvent } from "./types";
import { WeekHeader } from "./WeekHeader";

interface WeekViewProps {
	events: CalendarEvent[];
	weekStart: Date;
	onEventClick: (event: CalendarEvent) => void;
	onEventHover?: (event: CalendarEvent | null) => void;
	focusedDay?: Date;
	className?: string;
}

function isSameDay(date1: Date, date2: Date): boolean {
	return (
		date1.getFullYear() === date2.getFullYear() &&
		date1.getMonth() === date2.getMonth() &&
		date1.getDate() === date2.getDate()
	);
}

function isWeekend(dayIndex: number): boolean {
	return dayIndex === 0 || dayIndex === 6;
}

function getEventsForDay(events: CalendarEvent[], date: Date): CalendarEvent[] {
	return events
		.filter((event) => isSameDay(event.startTime, date))
		.sort((a, b) => a.startTime.getTime() - b.startTime.getTime());
}

function formatMonthYear(date: Date): string {
	return date
		.toLocaleDateString("en-US", {
			month: "long",
			year: "numeric",
		})
		.toUpperCase();
}

export function WeekView({
	events,
	weekStart,
	onEventClick,
	onEventHover,
	focusedDay,
	className,
}: WeekViewProps) {
	const today = new Date();
	const [hoveredEvent, setHoveredEvent] = useState<CalendarEvent | null>(null);
	const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);

	const handleEventHover = useCallback(
		(event: CalendarEvent | null, element?: HTMLElement) => {
			setHoveredEvent(event);
			if (event && element) {
				setAnchorRect(element.getBoundingClientRect());
			} else {
				setAnchorRect(null);
			}
			onEventHover?.(event);
		},
		[onEventHover],
	);

	const days = Array.from({ length: 7 }, (_, i) => {
		const date = new Date(weekStart);
		date.setDate(weekStart.getDate() + i);
		return date;
	});

	return (
		<div className={cn("paper-card w-full overflow-hidden", className)}>
			{/* Month indicator */}
			<div className="flex items-center justify-between border-b-2 border-text-primary bg-bg-white px-4 py-3">
				<span
					className="tagline tape-accent inline-flex items-center rounded bg-brand-100 px-2 py-1"
					style={{ "--cc-rotate": "1deg" } as React.CSSProperties}
				>
					{formatMonthYear(weekStart)}
				</span>
			</div>

			{/* Week header */}
			<WeekHeader weekStart={weekStart} />

			{/* Day columns with events */}
			<div className="grid grid-cols-7 bg-grid-paper">
				{days.map((date, index) => {
					const dayEvents = getEventsForDay(events, date);
					const isCurrentDay = isSameDay(date, today);
					const weekend = isWeekend(index);
					const isFocused = focusedDay && isSameDay(date, focusedDay);

					return (
						<DayColumn
							key={date.toISOString()}
							date={date}
							isWeekend={weekend}
							isToday={isCurrentDay}
							eventCount={dayEvents.length}
							className={cn(
								isFocused &&
									"outline-2 outline-offset-[-2px] outline-brand-green",
							)}
						>
							{dayEvents.map((event) => (
								<EventCard
									key={event.id}
									event={event}
									onClick={onEventClick}
									onHover={handleEventHover}
								/>
							))}
						</DayColumn>
					);
				})}
			</div>

			{/* Event peek tooltip */}
			<EventPeek event={hoveredEvent} anchorRect={anchorRect} />
		</div>
	);
}
