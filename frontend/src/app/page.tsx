"use client";

import { useRouter } from "next/navigation";
import { DiscoveryChat } from "@/components/discovery";
import { Hero, PaperQuote } from "@/components/layout";

export default function Home() {
	const router = useRouter();

	const handleSearch = (query: unknown) => {
		console.log("Search:", query);
	};

	const handleResultsReady = (events: unknown[]) => {
		console.log("Results ready:", events.length);
	};

	const handleViewWeek = () => {
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
