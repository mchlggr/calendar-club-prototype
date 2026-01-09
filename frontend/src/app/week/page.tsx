"use client";

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

	const handleEventClick = (event: CalendarEvent) => {
		console.log("Event clicked:", event.id);
	};

	const handleEventHover = (event: CalendarEvent | null) => {
		if (event) {
			console.log("Event hover:", event.id);
		}
	};

	return (
		<div className="min-h-screen px-6 py-8 md:px-12">
			<div className="mx-auto max-w-6xl">
				{/* Navigation */}
				<div className="mb-6 flex items-center justify-between">
					<button
						type="button"
						onClick={handlePrevWeek}
						className="rounded-lg border border-border-light bg-bg-white px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-cream"
					>
						Previous Week
					</button>
					<h1 className="text-lg font-semibold text-text-primary">
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
						className="rounded-lg border border-border-light bg-bg-white px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-cream"
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
							No events yet. Use the discovery chat to find events!
						</p>
					</div>
				)}
			</div>
		</div>
	);
}
