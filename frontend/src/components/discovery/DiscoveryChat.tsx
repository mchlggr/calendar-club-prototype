"use client";

import { useCallback, useRef, useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import {
	type CalendarEvent as ApiCalendarEvent,
	api,
	type ChatStreamEvent,
	type QuickPickOption,
} from "@/lib/api";
import { trackChatMessage, trackEventsDiscovered } from "@/lib/posthog";
import { cn } from "@/lib/utils";
import { ChatInput } from "./ChatInput";
import { QuickPicks } from "./QuickPicks";
import { ResultsPreview } from "./ResultsPreview";

interface SearchQuery {
	rawText: string;
	parsedIntent: {
		timeWindow?: { start: Date; end: Date };
		categories?: string[];
		maxDistance?: number;
		freeOnly?: boolean;
	};
}

interface DiscoveryChatProps {
	onSearch: (query: SearchQuery) => void;
	onResultsReady: (events: CalendarEvent[]) => void;
	onViewWeek: () => void;
	initialQuery?: string;
	className?: string;
}

interface ChatMessage {
	id: string;
	role: "user" | "agent";
	content: string;
}

/**
 * Maps API CalendarEvent to component CalendarEvent type
 */
function mapApiEventToCalendarEvent(event: ApiCalendarEvent): CalendarEvent {
	// Map API categories to component category enum
	const categoryMap: Record<string, CalendarEvent["category"]> = {
		ai: "ai",
		tech: "ai",
		startup: "startup",
		startups: "startup",
		community: "community",
		meetup: "meetup",
	};

	const firstCategory = event.categories?.[0]?.toLowerCase() || "meetup";
	const category = categoryMap[firstCategory] || "meetup";

	return {
		id: event.id,
		title: event.title,
		startTime: event.startTime,
		endTime: event.endTime || new Date(event.startTime.getTime() + 7200000), // Default 2 hours
		category,
		venue: event.location,
		canonicalUrl: event.url || event.sourceUrl || "",
		sourceId: event.source,
	};
}

export function DiscoveryChat({
	onSearch,
	onResultsReady,
	onViewWeek,
	initialQuery = "",
	className,
}: DiscoveryChatProps) {
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const [isProcessing, setIsProcessing] = useState(false);
	const [pendingResults, setPendingResults] = useState<CalendarEvent[]>([]);
	const [streamingMessage, setStreamingMessage] = useState<string>("");
	const [sessionId] = useState(() => crypto.randomUUID());
	// null = show static defaults, [] = hide quick picks, [...] = show LLM picks
	const [quickPicks, setQuickPicks] = useState<QuickPickOption[] | null>(null);
	const streamAbortRef = useRef<{ abort: () => void } | null>(null);

	const startChatStream = useCallback(
		(userQuery: string) => {
			// Abort any existing stream
			streamAbortRef.current?.abort();
			setStreamingMessage("");
			setIsProcessing(true);
			// Hide quick picks while processing
			setQuickPicks([]);

			const handleChunk = (event: ChatStreamEvent) => {
				if (event.type === "content" && event.content) {
					setStreamingMessage((prev) => prev + event.content);
				} else if (event.type === "quick_picks" && event.quick_picks) {
					// LLM sent dynamic quick picks
					setQuickPicks(event.quick_picks);
				} else if (event.type === "ready_to_search") {
					// LLM indicates it's ready to search - we can trigger search now
					// For now, just hide quick picks and wait for results
					setQuickPicks([]);
				} else if (event.type === "events" && event.events) {
					// Real events from backend - map to component type
					const mappedEvents = event.events.map(mapApiEventToCalendarEvent);
					setPendingResults(mappedEvents);
					onResultsReady(mappedEvents);
					trackEventsDiscovered({
						count: mappedEvents.length,
						query: userQuery,
					});
				} else if (event.type === "done") {
					// Stream complete - add full message
					setStreamingMessage((prev) => {
						if (prev) {
							setMessages((msgs) => [
								...msgs,
								{
									id: crypto.randomUUID(),
									role: "agent",
									content: prev,
								},
							]);
						}
						return "";
					});
					setIsProcessing(false);

					// If no events were sent, show mock results for now
					if (pendingResults.length === 0) {
						const mockResults: CalendarEvent[] = [
							{
								id: "1",
								title: "AI/ML Meetup: Large Language Models",
								startTime: new Date(Date.now() + 86400000),
								endTime: new Date(Date.now() + 86400000 + 7200000),
								category: "ai",
								venue: "Tech Hub",
								neighborhood: "Downtown",
								canonicalUrl: "https://example.com/event/1",
								sourceId: "meetup-1",
							},
							{
								id: "2",
								title: "Startup Pitch Night",
								startTime: new Date(Date.now() + 172800000),
								endTime: new Date(Date.now() + 172800000 + 10800000),
								category: "startup",
								venue: "Innovation Center",
								neighborhood: "University District",
								canonicalUrl: "https://example.com/event/2",
								sourceId: "meetup-2",
							},
							{
								id: "3",
								title: "Community Tech Talks",
								startTime: new Date(Date.now() + 259200000),
								endTime: new Date(Date.now() + 259200000 + 7200000),
								category: "community",
								venue: "Public Library",
								neighborhood: "Midtown",
								canonicalUrl: "https://example.com/event/3",
								sourceId: "meetup-3",
							},
						];
						setPendingResults(mockResults);
						onResultsReady(mockResults);
						trackEventsDiscovered({ count: mockResults.length });
					}
				} else if (event.type === "error") {
					setMessages((prev) => [
						...prev,
						{
							id: crypto.randomUUID(),
							role: "agent",
							content: `Sorry, there was an error: ${event.error}`,
						},
					]);
					setStreamingMessage("");
					setIsProcessing(false);
					// Show static quick picks again on error
					setQuickPicks(null);
				}
			};

			const handleError = (error: Error) => {
				setMessages((prev) => [
					...prev,
					{
						id: crypto.randomUUID(),
						role: "agent",
						content: `Sorry, there was an error: ${error.message}`,
					},
				]);
				setStreamingMessage("");
				setIsProcessing(false);
				// Show static quick picks again on error
				setQuickPicks(null);
			};

			streamAbortRef.current = api.chatStream(
				{ sessionId, message: userQuery },
				handleChunk,
				handleError,
			);
		},
		[sessionId, onResultsReady, pendingResults.length],
	);

	// Unified handler for both text input and quick pick selection
	const handleUserInput = useCallback(
		(input: string) => {
			// Add user message
			setMessages((prev) => [
				...prev,
				{ id: crypto.randomUUID(), role: "user", content: input },
			]);

			// Track chat message
			trackChatMessage({ sessionId, messageLength: input.length });

			// Notify parent of search
			const searchQuery: SearchQuery = {
				rawText: input,
				parsedIntent: {},
			};
			onSearch(searchQuery);

			// Start the chat stream
			startChatStream(input);
		},
		[sessionId, onSearch, startChatStream],
	);

	const handleRefine = () => {
		// Clear results and show quick picks again
		setPendingResults([]);
		setQuickPicks(null);
	};

	// Determine if we should show results
	const showResults = !isProcessing && pendingResults.length > 0;
	// Determine if we should show input (when not processing and no results)
	const showInput = !isProcessing && !showResults;

	return (
		<div
			className={cn(
				"flex flex-col gap-6 rounded-xl border border-border-light bg-bg-white p-6 shadow-md",
				className,
			)}
		>
			{/* Chat messages */}
			{messages.length > 0 && (
				<div className="flex flex-col gap-4">
					{messages.map((message) => (
						<div
							key={message.id}
							className={cn(
								"max-w-md rounded-lg px-4 py-3",
								message.role === "user"
									? "ml-auto border-l-[3px] border-accent-orange bg-bg-cream"
									: "border-l-[3px] border-brand-green bg-bg-white shadow-sm",
							)}
						>
							<p className="text-sm text-text-primary">{message.content}</p>
						</div>
					))}
				</div>
			)}

			{/* Input area with quick picks */}
			{showInput && (
				<div className="flex flex-col gap-4">
					<ChatInput onSubmit={handleUserInput} defaultValue={initialQuery} />
					{/* Show quick picks: null = defaults, [] = hide, [...] = LLM picks */}
					{quickPicks !== null && quickPicks.length === 0 ? null : (
						<div>
							<p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
								Quick picks
							</p>
							<QuickPicks
								options={quickPicks ?? undefined}
								onSelect={handleUserInput}
							/>
						</div>
					)}
				</div>
			)}

			{/* Processing state */}
			{isProcessing && (
				<div className="flex flex-col gap-3 rounded-lg bg-bg-cream p-4">
					<div className="flex items-center gap-3">
						<div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-green border-t-transparent" />
						<p className="text-sm text-text-secondary">
							{streamingMessage ? "Thinking..." : "Searching through events..."}
						</p>
					</div>
					{streamingMessage && (
						<div className="rounded-lg border-l-[3px] border-brand-green bg-bg-white px-4 py-3 shadow-sm">
							<p className="whitespace-pre-wrap text-sm text-text-primary">
								{streamingMessage}
								<span className="ml-1 inline-block h-4 w-2 animate-pulse bg-brand-green" />
							</p>
						</div>
					)}
					{/* Show LLM quick picks during processing if available */}
					{quickPicks && quickPicks.length > 0 && (
						<div className="mt-2">
							<p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
								Or try these
							</p>
							<QuickPicks options={quickPicks} onSelect={handleUserInput} />
						</div>
					)}
				</div>
			)}

			{/* Results */}
			{showResults && (
				<ResultsPreview
					events={pendingResults}
					totalCount={pendingResults.length}
					onViewWeek={onViewWeek}
					onRefine={handleRefine}
				/>
			)}
		</div>
	);
}
