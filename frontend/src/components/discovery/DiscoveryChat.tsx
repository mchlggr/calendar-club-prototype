"use client";

import { useCallback, useRef, useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import { api, type ChatStreamEvent } from "@/lib/api";
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

					// For now, show mock results until we have real event search
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
				setMessages((prev) => [
					...prev,
					{
						id: crypto.randomUUID(),
						role: "agent",
						content: `Sorry, there was an error: ${error.message}`,
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

			{/* State-specific content */}
			{state === "initial" && (
				<div className="flex flex-col gap-4">
					<ChatInput onSubmit={handleSubmit} defaultValue={initialQuery} />
					<div>
						<p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
							Quick picks
						</p>
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
						<div className="border-l-[3px] border-brand-green bg-bg-white px-4 py-3 shadow-sm rounded-lg">
							<p className="text-sm text-text-primary whitespace-pre-wrap">
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
