"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import { DiscoveryChat } from "@/components/discovery";
import { Hero, PaperQuote } from "@/components/layout";

export default function Home() {
	const router = useRouter();
	const [discoveredEvents, setDiscoveredEvents] = useState<CalendarEvent[]>([]);

	const handleSearch = (_query: unknown) => {
		// Search handled by DiscoveryChat streaming
	};

	const handleResultsReady = (events: CalendarEvent[]) => {
		setDiscoveredEvents(events);
	};

	const handleViewWeek = () => {
		if (discoveredEvents.length > 0) {
			sessionStorage.setItem(
				"discoveredEvents",
				JSON.stringify(discoveredEvents),
			);
		}
		router.push("/week");
	};

	return (
		<div className="min-h-screen px-6 py-12 md:px-12">
			<div className="mx-auto max-w-2xl">
				{/* Hero Section */}
				<div className="mb-8">
					<Hero />
					<PaperQuote className="mt-6" />
				</div>

				{/* Discovery Chat */}
				<DiscoveryChat
					onSearch={handleSearch}
					onResultsReady={handleResultsReady}
					onViewWeek={handleViewWeek}
				/>
			</div>
		</div>
	);
}
