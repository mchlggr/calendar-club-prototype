"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type CalendarEvent, WeekView } from "@/components/calendar";

function getWeekStart(date: Date): Date {
	const d = new Date(date);
	const day = d.getDay();
	d.setDate(d.getDate() - day);
	d.setHours(0, 0, 0, 0);
	return d;
}

export default function WeekPage() {
	const [weekStart, setWeekStart] = useState(() => getWeekStart(new Date()));
	const [events, setEvents] = useState<CalendarEvent[]>([]);

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
							: new Date(startTime.getTime() + 2 * 60 * 60 * 1000); // Default 2 hours
						return {
							...e,
							startTime,
							endTime,
						} as CalendarEvent;
					},
				);
				setEvents(loadedEvents);

				// Auto-navigate to the week containing the first event
				if (loadedEvents.length > 0) {
					const firstEventDate = loadedEvents.reduce(
						(earliest: Date, event: CalendarEvent) =>
							event.startTime < earliest ? event.startTime : earliest,
						loadedEvents[0].startTime,
					);
					setWeekStart(getWeekStart(firstEventDate));
				}
			} catch (error) {
				console.error("Failed to parse stored events:", error);
			}
		}
	}, []);

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

	const handleEventClick = (_event: CalendarEvent) => {
		// Event click handling - could open modal or navigate
	};

	const handleEventHover = (_event: CalendarEvent | null) => {
		// Event hover handling - could show preview
	};

	return (
		<div className="min-h-screen px-6 py-8 md:px-12">
			<div className="mx-auto max-w-6xl">
				{/* Navigation */}
				<div className="mb-6 flex items-center justify-between">
					<button
						type="button"
						onClick={handlePrevWeek}
						className="btn-brutal cc-btn-secondary hover:bg-accent-yellow/30"
					>
						Previous Week
					</button>
					<h1 className="cc-h2 text-text-primary">
						Week of{" "}
						{weekStart.toLocaleDateString("en-US", {
							month: "long",
							day: "numeric",
							year: "numeric",
						})}
					</h1>
					<button
						type="button"
						onClick={handleNextWeek}
						className="btn-brutal cc-btn-secondary hover:bg-accent-yellow/30"
					>
						Next Week
					</button>
				</div>

				{/* Week View */}
				<WeekView
					events={events}
					weekStart={weekStart}
					onEventClick={handleEventClick}
					onEventHover={handleEventHover}
				/>

				{/* Empty state */}
				{events.length === 0 && (
					<div className="mt-8 text-center">
						<p className="text-text-secondary">
							No events yet.{" "}
							<Link
								href="/"
								className="underline decoration-border-light underline-offset-4 hover:decoration-text-secondary"
							>
								Go back to Discover
							</Link>{" "}
							to search.
						</p>
					</div>
				)}
			</div>
		</div>
	);
}
