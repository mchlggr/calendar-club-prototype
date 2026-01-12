/**
 * API client for Calendar Club.
 *
 * Only includes endpoints that are actually used by the frontend UI.
 */

import { debugLog, debugWarn } from "./debug";

// =============================================================================
// Types
// =============================================================================

export interface DiscoveryEventWire {
	id: string;
	title: string;
	description?: string;
	startTime: string;
	endTime?: string;
	location?: string;
	url?: string;
	source: string;
	sourceUrl?: string;
	categories?: string[];
	imageUrl?: string;
	price?: {
		isFree: boolean;
		amount?: number;
		currency?: string;
	};
}

export interface ChatMessage {
	role: "user" | "assistant";
	content: string;
}

export interface ChatStreamRequest {
	sessionId: string;
	message: string;
	history?: ChatMessage[];
}

export interface QuickPickOption {
	label: string;
	value: string;
}

export interface ChatStreamEvent {
	type:
		| "content"
		| "done"
		| "error"
		| "events"
		| "more_events"
		| "background_search"
		| "action"
		| "phase"
		| "quick_picks"
		| "placeholder"
		| "ready_to_search"
		| "searching";
	content?: string;
	message?: string;
	error?: string;
	quick_picks?: QuickPickOption[];
	placeholder?: string;
	events?: DiscoveryEventWire[];
	phase?: string;
	action?: string;
	source?: string;
	trace_id?: string;
}

export interface CalendarExportEvent {
	title: string;
	start: string;
	end?: string;
	description?: string;
	location?: string;
	url?: string;
}

// =============================================================================
// Error Handling
// =============================================================================

export class ApiError extends Error {
	constructor(
		message: string,
		public status: number,
		public code?: string,
	) {
		super(message);
		this.name = "ApiError";
	}
}

export class NetworkError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "NetworkError";
	}
}

// =============================================================================
// Configuration
// =============================================================================

const getBaseUrl = (): string => {
	// In the browser, use relative URLs (same origin)
	if (typeof window !== "undefined") {
		return "";
	}
	// Server-side: use environment variable or default
	return process.env.NEXT_PUBLIC_API_URL || "";
};

// =============================================================================
// API Client
// =============================================================================

export const api = {
	/**
	 * POST /api/chat/stream - Stream chat responses via SSE
	 */
	chatStream(
		request: ChatStreamRequest,
		onChunk: (event: ChatStreamEvent) => void,
		onError?: (error: Error) => void,
	): { abort: () => void } {
		const baseUrl = getBaseUrl();
		const controller = new AbortController();

		(async () => {
			try {
				const response = await fetch(`${baseUrl}/api/chat/stream`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
					},
					body: JSON.stringify({
						session_id: request.sessionId,
						message: request.message,
						history: request.history || [],
					}),
					signal: controller.signal,
				});

				if (!response.ok) {
					throw new ApiError(
						`Stream request failed with status ${response.status}`,
						response.status,
					);
				}

				const reader = response.body?.getReader();
				if (!reader) {
					throw new NetworkError("No response body");
				}

				const decoder = new TextDecoder();
				let buffer = "";

				while (true) {
					const { done, value } = await reader.read();
					if (done) break;

					buffer += decoder.decode(value, { stream: true });

					// Parse SSE events from buffer
					const lines = buffer.split("\n");
					buffer = lines.pop() || "";

					for (const line of lines) {
						if (!line.startsWith("data: ")) continue;
						try {
							const data = JSON.parse(line.slice(6)) as ChatStreamEvent;
							debugLog("SSE", "Event received", {
								type: data.type,
								hasEvents: !!data.events,
								eventCount: data.events?.length,
							});
							onChunk(data);
						} catch (e) {
							// Only skip JSON parsing errors, re-throw other errors
							if (e instanceof SyntaxError) {
								debugWarn("SSE", "JSON parse error (skipped)", {
									line: line.slice(0, 100),
								});
								continue;
							}
							throw e;
						}
					}
				}
			} catch (error) {
				if (error instanceof DOMException && error.name === "AbortError") {
					return;
				}
				onError?.(error instanceof Error ? error : new Error(String(error)));
			}
		})();

		return { abort: () => controller.abort() };
	},

	/**
	 * POST /api/calendar/export-multiple - Export multiple events as ICS file
	 */
	async exportEvents(events: CalendarExportEvent[]): Promise<void> {
		const baseUrl = getBaseUrl();
		const response = await fetch(`${baseUrl}/api/calendar/export-multiple`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({ events }),
		});

		if (!response.ok) {
			throw new ApiError(
				`Export failed with status ${response.status}`,
				response.status,
			);
		}

		// Download the ICS file
		const blob = await response.blob();
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = "calendar-club-events.ics";
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	},
};

export default api;
