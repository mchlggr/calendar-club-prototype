"use client";

import { useCallback, useRef, useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import {
	api,
	type ChatStreamEvent,
	type DiscoveryEventWire,
	type QuickPickOption,
} from "@/lib/api";
import { debugLog } from "@/lib/debug";
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
	events?: CalendarEvent[];
}

/**
 * Maps API DiscoveryEventWire to component CalendarEvent type.
 * Handles date string parsing since API sends ISO strings, not Date objects.
 */
function mapApiEventToCalendarEvent(event: DiscoveryEventWire): CalendarEvent {
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

	// Parse date strings to Date objects (API sends ISO strings)
	const startTime = new Date(event.startTime);
	const endTime = event.endTime
		? new Date(event.endTime)
		: new Date(startTime.getTime() + 7200000); // Default 2 hours

	return {
		id: event.id,
		title: event.title,
		startTime,
		endTime,
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
	const [isSearching, setIsSearching] = useState(false);
	// Dynamic placeholder from LLM, null = use default
	const [dynamicPlaceholder, setDynamicPlaceholder] = useState<string | null>(
		null,
	);
	const streamAbortRef = useRef<{ abort: () => void } | null>(null);
	const streamingMessageRef = useRef<string>("");
	const hasProcessedDoneRef = useRef<boolean>(false);
	const pendingResultsRef = useRef<CalendarEvent[]>([]);

	const startChatStream = useCallback(
		(userQuery: string, historyMessages: ChatMessage[]) => {
			// Abort any existing stream
			streamAbortRef.current?.abort();
			setStreamingMessage("");
			streamingMessageRef.current = "";
			hasProcessedDoneRef.current = false;
			pendingResultsRef.current = [];
			// Clear stale events from previous response before showing thinking state
			setPendingResults([]);
			setIsProcessing(true);
			setIsSearching(false);
			// Hide quick picks while processing
			setQuickPicks([]);

			const handleChunk = (event: ChatStreamEvent) => {
				if (event.type === "content" && event.content) {
					// Track content in ref for reliable "done" handling
					streamingMessageRef.current += event.content;
					setStreamingMessage(streamingMessageRef.current);
				} else if (event.type === "searching") {
					// Backend is now searching - show searching state
					setIsSearching(true);
				} else if (event.type === "quick_picks" && event.quick_picks) {
					// LLM sent dynamic quick picks
					setQuickPicks(event.quick_picks);
				} else if (event.type === "placeholder" && event.placeholder) {
					// LLM sent dynamic placeholder for input
					setDynamicPlaceholder(event.placeholder);
				} else if (event.type === "ready_to_search") {
					// LLM indicates it's ready to search - we can trigger search now
					// For now, just hide quick picks and wait for results
					setQuickPicks([]);
				} else if (event.type === "events" && event.events) {
					// Real events from backend - map to component type
					const traceId = event.trace_id || "unknown";
					debugLog("Events", "Received from backend", {
						trace: traceId,
						count: event.events.length,
					});

					// Log individual events before mapping
					event.events.forEach((ev, i) => {
						debugLog("Events", `Raw event ${i}`, {
							id: ev.id,
							title: ev.title?.slice(0, 50),
							startTime: ev.startTime,
						});
					});

					const mappedEvents = event.events.map(mapApiEventToCalendarEvent);

					debugLog("Events", "Mapped to calendar format", {
						count: mappedEvents.length,
					});

					setPendingResults(mappedEvents);
					pendingResultsRef.current = mappedEvents;
					onResultsReady(mappedEvents);
					trackEventsDiscovered({
						count: mappedEvents.length,
						query: userQuery,
					});
				} else if (event.type === "more_events" && event.events) {
					// Background discovery results - merge with existing
					debugLog("Events", "Background discovery results", {
						count: event.events.length,
						source: event.source,
					});

					const mappedEvents = event.events.map(mapApiEventToCalendarEvent);

					// Merge with existing results, avoiding duplicates
					setPendingResults((prev) => {
						const existingIds = new Set(prev.map((e) => e.id));
						const newEvents = mappedEvents.filter(
							(e) => !existingIds.has(e.id),
						);
						debugLog("Events", "Merged background results", {
							existing: prev.length,
							new: newEvents.length,
							total: prev.length + newEvents.length,
						});
						const merged = [...prev, ...newEvents];
						pendingResultsRef.current = merged;
						return merged;
					});

					// Notify parent of updated results
					onResultsReady(mappedEvents);

					trackEventsDiscovered({
						count: mappedEvents.length,
					});
				} else if (event.type === "background_search") {
					// Background search started notification
					debugLog("Events", "Background search started", {
						message: event.message,
					});
				} else if (event.type === "done") {
					// Guard against duplicate "done" events (React StrictMode, etc.)
					if (hasProcessedDoneRef.current) return;
					hasProcessedDoneRef.current = true;

					// Stream complete - add full message with events using ref values
					const finalMessage = streamingMessageRef.current;
					const finalEvents = pendingResultsRef.current;
					if (finalMessage) {
						setMessages((msgs) => [
							...msgs,
							{
								id: crypto.randomUUID(),
								role: "agent",
								content: finalMessage,
								// Capture events with this message for history persistence
								events: finalEvents.length > 0 ? finalEvents : undefined,
							},
						]);
					}
					setStreamingMessage("");
					streamingMessageRef.current = "";
					setIsProcessing(false);
					setIsSearching(false);
					// NO MOCK DATA - if no events found, show empty state
					// All events must come from real API sources (Eventbrite, etc.)
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

			// Convert internal message format to API format (agent -> assistant)
			const apiHistory = historyMessages.map((msg) => ({
				role: msg.role === "agent" ? "assistant" : msg.role,
				content: msg.content,
			})) as { role: "user" | "assistant"; content: string }[];

			streamAbortRef.current = api.chatStream(
				{ sessionId, message: userQuery, history: apiHistory },
				handleChunk,
				handleError,
			);
		},
		[sessionId, onResultsReady],
	);

	// Unified handler for both text input and quick pick selection
	const handleUserInput = useCallback(
		(input: string) => {
			// Create the new user message
			const newUserMessage: ChatMessage = {
				id: crypto.randomUUID(),
				role: "user",
				content: input,
			};

			// Build history: current messages (NOT including new user message,
			// since backend adds message separately to the history)
			const historyForApi = [...messages];

			// Add user message to state
			setMessages((prev) => [...prev, newUserMessage]);

			// Track chat message
			trackChatMessage({ sessionId, messageLength: input.length });

			// Notify parent of search
			const searchQuery: SearchQuery = {
				rawText: input,
				parsedIntent: {},
			};
			onSearch(searchQuery);

			// Start the chat stream with full history
			startChatStream(input, historyForApi);
		},
		[sessionId, onSearch, startChatStream, messages],
	);

	// Check if the most recent message has events (for placeholder logic)
	const lastMessageHasEvents =
		messages.length > 0 &&
		messages[messages.length - 1].events &&
		(messages[messages.length - 1].events?.length ?? 0) > 0;
	// Show "narrow it down" placeholder if we have results (either in last message or streaming)
	const hasResults =
		lastMessageHasEvents || (isProcessing && pendingResults.length > 0);

	return (
		<div
			className={cn(
				"flex flex-col gap-6 rounded-xl border border-border-light bg-grid-paper p-6 shadow-md",
				className,
			)}
		>
			{/* Chat messages - including streaming response and results */}
			{(messages.length > 0 || isProcessing) && (
				<div className="flex flex-col gap-4">
					{/* Past messages with inline events */}
					{messages.map((message) => (
						<div key={message.id} className="flex flex-col gap-2">
							<div
								className={cn(
									"max-w-md rounded-lg px-4 py-3",
									message.role === "user"
										? "ml-auto bg-accent-orange text-white"
										: "bg-brand-100 text-text-primary shadow-sm",
								)}
							>
								<p className="text-sm">{message.content}</p>
							</div>
							{/* Show events inline with agent messages that have them */}
							{message.role === "agent" &&
								message.events &&
								message.events.length > 0 && (
									<ResultsPreview
										events={message.events}
										totalCount={message.events.length}
										onViewWeek={onViewWeek}
									/>
								)}
						</div>
					))}

					{/* Streaming response bubble */}
					{isProcessing && (
						<div className="max-w-md rounded-lg bg-brand-100 px-4 py-3 shadow-sm">
							{streamingMessage ? (
								<p className="whitespace-pre-wrap text-sm text-text-primary">
									{streamingMessage}
									<span className="ml-1 inline-block h-4 w-2 animate-pulse bg-brand-green" />
								</p>
							) : isSearching ? (
								<div className="flex items-center gap-3">
									<svg
										className="h-5 w-5 animate-pulse text-brand-green"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										role="img"
										aria-label="Searching"
									>
										<path
											strokeLinecap="round"
											strokeLinejoin="round"
											strokeWidth={2}
											d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
										/>
									</svg>
									<p className="text-sm font-medium text-brand-green">
										Searching events...
									</p>
								</div>
							) : (
								<div className="flex items-center gap-2">
									<div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-green border-t-transparent" />
									<p className="text-sm text-text-secondary">Thinking...</p>
								</div>
							)}
						</div>
					)}

					{/* Live results preview during streaming */}
					{isProcessing && pendingResults.length > 0 && (
						<ResultsPreview
							events={pendingResults}
							totalCount={pendingResults.length}
							onViewWeek={onViewWeek}
						/>
					)}
				</div>
			)}

			{/* Quick picks - above input */}
			{!isProcessing && (quickPicks === null || quickPicks.length > 0) && (
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

			{/* Input - ALWAYS at the bottom */}
			<ChatInput
				onSubmit={handleUserInput}
				defaultValue={initialQuery}
				disabled={isProcessing}
				placeholder={
					dynamicPlaceholder ??
					(hasResults ? "Narrow it down..." : "Search events...")
				}
			/>
		</div>
	);
}
