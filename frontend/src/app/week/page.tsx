"use client";

import { useState } from "react";
import { type CalendarEvent, WeekView } from "@/components/calendar";

function getWeekStart(date: Date): Date {
	const d = new Date(date);
	const day = d.getDay();
	d.setDate(d.getDate() - day);
	d.setHours(0, 0, 0, 0);
	return d;
}

const mockEvents: CalendarEvent[] = [
	{
		id: "1",
		title: "AI/ML Meetup: Large Language Models",
		startTime: new Date(Date.now() + 86400000 + 36000000),
		endTime: new Date(Date.now() + 86400000 + 43200000),
		category: "ai",
		venue: "Tech Hub",
		neighborhood: "Downtown",
		canonicalUrl: "https://example.com/event/1",
		sourceId: "meetup-1",
	},
	{
		id: "2",
		title: "Startup Pitch Night",
		startTime: new Date(Date.now() + 172800000 + 61200000),
		endTime: new Date(Date.now() + 172800000 + 72000000),
		category: "startup",
		venue: "Innovation Center",
		neighborhood: "University District",
		canonicalUrl: "https://example.com/event/2",
		sourceId: "meetup-2",
	},
	{
		id: "3",
		title: "Community Tech Talks",
		startTime: new Date(Date.now() + 259200000 + 32400000),
		endTime: new Date(Date.now() + 259200000 + 39600000),
		category: "community",
		venue: "Public Library",
		neighborhood: "Midtown",
		canonicalUrl: "https://example.com/event/3",
		sourceId: "meetup-3",
	},
	{
		id: "4",
		title: "React Developer Meetup",
		startTime: new Date(Date.now() + 345600000 + 64800000),
		endTime: new Date(Date.now() + 345600000 + 75600000),
		category: "meetup",
		venue: "Coworking Space",
		neighborhood: "East Side",
		canonicalUrl: "https://example.com/event/4",
		sourceId: "meetup-4",
	},
];

export default function WeekPage() {
	const [weekStart, setWeekStart] = useState(() => getWeekStart(new Date()));

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
					events={mockEvents}
					weekStart={weekStart}
					onEventClick={handleEventClick}
					onEventHover={handleEventHover}
				/>
			</div>
		</div>
	);
}
