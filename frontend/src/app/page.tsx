"use client";

import { useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import { DiscoveryChat } from "@/components/discovery";
import { Hero, PaperQuote } from "@/components/layout";

export default function Home() {
	const [discoveredEvents, setDiscoveredEvents] = useState<CalendarEvent[]>([]);

	const handleSearch = (_query: unknown) => {
		// Search handled by DiscoveryChat streaming
	};

	const handleResultsReady = (events: CalendarEvent[]) => {
		setDiscoveredEvents(events);
	};

	const prepareViewWeek = () => {
		// Store events before navigation (Link handles the actual navigation)
		if (discoveredEvents.length > 0) {
			sessionStorage.setItem(
				"discoveredEvents",
				JSON.stringify(discoveredEvents),
			);
		}
	};

	return (
		<div className="min-h-screen px-6 py-12 md:px-12">
			<div className="mx-auto max-w-2xl">
				{/* Hero Section */}
				<div className="mb-8">
					<Hero />
				</div>

				{/* Discovery Chat */}
				<DiscoveryChat
					onSearch={handleSearch}
					onResultsReady={handleResultsReady}
					onViewWeek={prepareViewWeek}
				/>
			</div>
		</div>
	);
}
