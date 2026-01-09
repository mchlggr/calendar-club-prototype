"use client";

import { useState } from "react";
import { type CalendarEvent, WeekView } from "@/components/calendar";
import { ChatInput } from "@/components/discovery/ChatInput";
import { FeaturedEventBanner, Hero, HighlightBox } from "@/components/layout";

// Mock events matching the design
const mockEvents: CalendarEvent[] = [
	{
		id: "1",
		title: "Logistics Breakfast Club",
		startTime: new Date(2025, 7, 31, 8, 0),
		endTime: new Date(2025, 7, 31, 10, 0),
		category: "meetup",
		venue: "Downtown Hub",
		canonicalUrl: "https://example.com/event/1",
		sourceId: "meetup-1",
	},
	{
		id: "2",
		title: "One Million Cups",
		startTime: new Date(2025, 7, 31, 8, 0),
		endTime: new Date(2025, 7, 31, 10, 0),
		category: "startup",
		venue: "Coffee House",
		canonicalUrl: "https://example.com/event/2",
		sourceId: "meetup-2",
	},
	{
		id: "3",
		title: "Code and Coffee",
		startTime: new Date(2025, 7, 31, 13, 0),
		endTime: new Date(2025, 7, 31, 15, 0),
		category: "community",
		venue: "Tech Center",
		canonicalUrl: "https://example.com/event/3",
		sourceId: "meetup-3",
	},
	{
		id: "4",
		title: "Code and Coffee",
		startTime: new Date(2025, 8, 1, 13, 0),
		endTime: new Date(2025, 8, 1, 15, 0),
		category: "startup",
		venue: "Startup Hub",
		canonicalUrl: "https://example.com/event/4",
		sourceId: "meetup-4",
	},
	{
		id: "5",
		title: "Founders Live",
		startTime: new Date(2025, 8, 1, 18, 0),
		endTime: new Date(2025, 8, 1, 21, 0),
		category: "startup",
		venue: "Innovation Center",
		canonicalUrl: "https://example.com/event/5",
		sourceId: "meetup-5",
	},
	{
		id: "6",
		title: "Tiger Talks: Build Your Know AI",
		startTime: new Date(2025, 8, 2, 11, 0),
		endTime: new Date(2025, 8, 2, 13, 0),
		category: "ai",
		venue: "University",
		canonicalUrl: "https://example.com/event/6",
		sourceId: "meetup-6",
	},
	{
		id: "7",
		title: "Law Lunch",
		startTime: new Date(2025, 8, 2, 11, 0),
		endTime: new Date(2025, 8, 2, 13, 0),
		category: "community",
		venue: "Law Center",
		canonicalUrl: "https://example.com/event/7",
		sourceId: "meetup-7",
	},
	{
		id: "8",
		title: "Code and Coffee",
		startTime: new Date(2025, 8, 2, 13, 0),
		endTime: new Date(2025, 8, 2, 15, 0),
		category: "startup",
		venue: "Cafe",
		canonicalUrl: "https://example.com/event/8",
		sourceId: "meetup-8",
	},
	{
		id: "9",
		title: "One Million Cups",
		startTime: new Date(2025, 8, 3, 8, 0),
		endTime: new Date(2025, 8, 3, 10, 0),
		category: "startup",
		venue: "Coffee House",
		canonicalUrl: "https://example.com/event/9",
		sourceId: "meetup-9",
	},
	{
		id: "10",
		title: "Code and Coffee",
		startTime: new Date(2025, 8, 3, 13, 0),
		endTime: new Date(2025, 8, 3, 15, 0),
		category: "community",
		venue: "Tech Center",
		canonicalUrl: "https://example.com/event/10",
		sourceId: "meetup-10",
	},
	{
		id: "11",
		title: "Ohio Tech Day",
		startTime: new Date(2025, 8, 4, 8, 0),
		endTime: new Date(2025, 8, 4, 17, 0),
		category: "startup",
		venue: "Convention Center",
		canonicalUrl: "https://example.com/event/11",
		sourceId: "meetup-11",
	},
	{
		id: "12",
		title: "Code and Coffee",
		startTime: new Date(2025, 8, 5, 13, 0),
		endTime: new Date(2025, 8, 5, 15, 0),
		category: "startup",
		venue: "Coffee Shop",
		canonicalUrl: "https://example.com/event/12",
		sourceId: "meetup-12",
	},
	{
		id: "13",
		title: "Founders Live",
		startTime: new Date(2025, 8, 6, 18, 0),
		endTime: new Date(2025, 8, 6, 21, 0),
		category: "community",
		venue: "Event Space",
		canonicalUrl: "https://example.com/event/13",
		sourceId: "meetup-13",
	},
];

export default function Home() {
	const [weekStart] = useState(() => new Date(2025, 7, 31)); // Aug 31, 2025

	const handleSearch = (query: string) => {
		console.log("Search:", query);
	};

	const handleEventClick = (event: CalendarEvent) => {
		console.log("Event clicked:", event.id);
	};

	return (
		<div className="min-h-screen bg-notebook-grid px-6 py-8 md:px-12">
			<div className="mx-auto max-w-6xl">
				{/* Hero Section with Quote and Search */}
				<div className="mb-8 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
					<div>
						<Hero />
						<HighlightBox className="mt-6">
							A curated directory of the best technical meetups. No noise, just
							deep cuts.
						</HighlightBox>
					</div>

					{/* Search Bar */}
					<div className="w-full md:w-80">
						<ChatInput onSubmit={handleSearch} />
					</div>
				</div>

				{/* Week Grid with Starts Here sticker */}
				<div className="relative mb-12">
					{/* Starts Here sticker */}
					<div className="sticker absolute -left-2 -top-4 z-10 text-sm">
						Starts Here!
					</div>

					<WeekView
						events={mockEvents}
						weekStart={weekStart}
						onEventClick={handleEventClick}
					/>
				</div>

				{/* Featured Event Banner */}
				<FeaturedEventBanner
					title="OHIO VC FEST"
					subtitle="Returning to Cleveland • Sep 17-18"
					ticketUrl="https://example.com/tickets"
				/>
			</div>
		</div>
	);
}
