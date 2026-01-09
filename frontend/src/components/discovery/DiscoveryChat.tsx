"use client";

import { useCallback, useRef, useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import {
	ApiError,
	api,
	type ChatStreamEvent,
	type EventResult,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChatInput } from "./ChatInput";
import { ClarifyingQ, type QuestionType } from "./ClarifyingQ";
import { QuickPicks } from "./QuickPicks";
import { ResultsPreview } from "./ResultsPreview";

type ChatState = "initial" | "clarifying" | "processing" | "results";

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

function transformEventResult(result: EventResult): CalendarEvent {
	return {
		id: result.id,
		title: result.title,
		startTime: new Date(result.date),
		endTime: new Date(new Date(result.date).getTime() + 2 * 60 * 60 * 1000),
		category: result.category as CalendarEvent["category"],
		venue: result.location,
		neighborhood: "",
		canonicalUrl: `https://example.com/e/${result.id}`,
		sourceId: result.id,
	};
}

export function DiscoveryChat({
	onSearch,
	onResultsReady,
	onViewWeek,
	initialQuery = "",
	className,
}: DiscoveryChatProps) {
	const [state, setState] = useState<ChatState>("initial");
	const [messages, setMessages] = useState<ChatMessage[]>([]);
	const [currentQuestion, setCurrentQuestion] = useState<QuestionType | null>(
		null,
	);
	const [pendingResults, setPendingResults] = useState<CalendarEvent[]>([]);
	const [streamingMessage, setStreamingMessage] = useState<string>("");
	const [sessionId] = useState(() => crypto.randomUUID());
	const streamAbortRef = useRef<{ abort: () => void } | null>(null);

	const startChatStream = useCallback(
		(userQuery: string) => {
			// Abort any existing stream
			streamAbortRef.current?.abort();
			setStreamingMessage("");
			setState("processing");

			const handleChunk = (event: ChatStreamEvent) => {
				if (event.type === "content" && event.content) {
					setStreamingMessage((prev) => prev + event.content);
				} else if (event.type === "events" && event.data) {
					// Convert EventResult to CalendarEvent and store
					const events = event.data.map(transformEventResult);
					setPendingResults(events);
					onResultsReady(events);
				} else if (event.type === "done") {
					// Stream complete - add full message and show results
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
					setState("results");
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
					setState("initial");
				}
			};

			const handleError = (error: Error) => {
				const hint =
					error instanceof ApiError && error.status === 404
						? " (Is the API running? In local dev, start FastAPI on :8000 and use the Next.js /api proxy.)"
						: "";
				setMessages((prev) => [
					...prev,
					{
						id: crypto.randomUUID(),
						role: "agent",
						content: `Sorry, there was an error: ${error.message}${hint}`,
					},
				]);
				setStreamingMessage("");
				setState("initial");
			};

			streamAbortRef.current = api.chatStream(
				{ sessionId, message: userQuery },
				handleChunk,
				handleError,
			);
		},
		[sessionId, onResultsReady],
	);

	const handleSubmit = (query: string) => {
		setMessages((prev) => [
			...prev,
			{ id: crypto.randomUUID(), role: "user", content: query },
		]);

		const searchQuery: SearchQuery = {
			rawText: query,
			parsedIntent: {},
		};

		onSearch(searchQuery);
		setState("clarifying");
		setCurrentQuestion("time");
	};

	const handleQuickPick = (value: string) => {
		const quickPickLabels: Record<string, string> = {
			"this-weekend": "this weekend",
			"ai-tech": "AI/Tech events",
			startups: "startup events",
			free: "free events",
		};
		handleSubmit(quickPickLabels[value] || value);
	};

	const handleClarifyAnswer = (value: string) => {
		const newMessages = [
			...messages,
			{ id: crypto.randomUUID(), role: "user" as const, content: value },
		];
		setMessages(newMessages);

		const questionOrder: QuestionType[] = [
			"time",
			"category",
			"location",
			"cost",
		];
		const currentIndex = currentQuestion
			? questionOrder.indexOf(currentQuestion)
			: -1;

		if (currentIndex < questionOrder.length - 1) {
			setCurrentQuestion(questionOrder[currentIndex + 1]);
		} else {
			// Build query from all user messages
			const userQuery = newMessages
				.filter((m) => m.role === "user")
				.map((m) => m.content)
				.join(". ");
			startChatStream(userQuery);
		}
	};

	const handleRefine = () => {
		setState("clarifying");
		setCurrentQuestion("category");
	};

	return (
		<div className={cn("flex flex-col gap-6 paper-card p-6", className)}>
			{/* Chat messages */}
			{messages.length > 0 && (
				<div className="flex flex-col gap-4">
					{messages.map((message) => (
						<div
							key={message.id}
							className={cn(
								"cc-bubble max-w-md",
								message.role === "user"
									? "ml-auto cc-bubble-user"
									: "cc-bubble-agent",
							)}
						>
							<p className="cc-body">{message.content}</p>
						</div>
					))}
				</div>
			)}

			{/* State-specific content */}
			{state === "initial" && (
				<div className="flex flex-col gap-4">
					<ChatInput onSubmit={handleSubmit} defaultValue={initialQuery} />
					<div>
						<p className="mb-2 cc-label-muted">Quick picks</p>
						<QuickPicks onSelect={handleQuickPick} />
					</div>
				</div>
			)}

			{state === "clarifying" && currentQuestion && (
				<ClarifyingQ
					questionType={currentQuestion}
					onAnswer={handleClarifyAnswer}
				/>
			)}

			{state === "processing" && (
				<div className="flex flex-col gap-3 rounded-lg bg-bg-cream p-4">
					<div className="flex items-center gap-3">
						<div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-green border-t-transparent" />
						<p className="text-sm text-text-secondary">
							{streamingMessage ? "Thinking..." : "Searching through events..."}
						</p>
					</div>
					{streamingMessage && (
						<div className="cc-bubble cc-bubble-agent">
							<p className="cc-body whitespace-pre-wrap">
								{streamingMessage}
								<span className="inline-block w-2 h-4 ml-1 bg-brand-green animate-pulse" />
							</p>
						</div>
					)}
				</div>
			)}

			{state === "results" && pendingResults.length > 0 && (
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
