/**
 * API Client for Calendar Club
 *
 * Fetch-based client with TypeScript types, error handling,
 * and retry logic for the Calendar Club backend.
 */

// =============================================================================
// Types
// =============================================================================

export interface CalendarEvent {
	id: string;
	title: string;
	description?: string;
	startTime: Date;
	endTime?: Date;
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

export interface SearchFilters {
	timeWindow?: {
		start: Date;
		end: Date;
	};
	categories?: string[];
	maxDistance?: number;
	freeOnly?: boolean;
}

export interface SearchRequest {
	query: string;
	filters?: SearchFilters;
}

export interface SearchResponse {
	events: CalendarEvent[];
	totalCount: number;
	searchId: string;
}

export interface ChatMessage {
	role: "user" | "assistant";
	content: string;
}

export interface ChatRequest {
	messages: ChatMessage[];
	sessionId?: string;
}

export interface ChatResponse {
	message: ChatMessage;
	sessionId: string;
	suggestedEvents?: CalendarEvent[];
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
		| "action"
		| "phase"
		| "quick_picks"
		| "placeholder"
		| "ready_to_search"
		| "searching";
	content?: string;
	error?: string;
	session_id: string;
	quick_picks?: QuickPickOption[];
	placeholder?: string;
	events?: CalendarEvent[];
	phase?: string;
	action?: string;
}

export interface EventsRequest {
	page?: number;
	limit?: number;
	category?: string;
	startDate?: Date;
	endDate?: Date;
}

export interface EventsResponse {
	events: CalendarEvent[];
	totalCount: number;
	page: number;
	totalPages: number;
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

const DEFAULT_TIMEOUT = 30000; // 30 seconds
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000; // 1 second

// =============================================================================
// Fetch Wrapper with Retry Logic
// =============================================================================

interface FetchOptions extends RequestInit {
	timeout?: number;
	retries?: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchWithRetry(
	url: string,
	options: FetchOptions = {},
): Promise<Response> {
	const {
		timeout = DEFAULT_TIMEOUT,
		retries = MAX_RETRIES,
		...fetchOptions
	} = options;

	let lastError: Error | null = null;

	for (let attempt = 0; attempt <= retries; attempt++) {
		try {
			const controller = new AbortController();
			const timeoutId = setTimeout(() => controller.abort(), timeout);

			const response = await fetch(url, {
				...fetchOptions,
				signal: controller.signal,
			});

			clearTimeout(timeoutId);

			// Don't retry client errors (4xx), only server errors (5xx)
			if (response.status >= 400 && response.status < 500) {
				const errorData = await response.json().catch(() => ({}));
				throw new ApiError(
					errorData.message || `Request failed with status ${response.status}`,
					response.status,
					errorData.code,
				);
			}

			if (!response.ok) {
				throw new ApiError(
					`Request failed with status ${response.status}`,
					response.status,
				);
			}

			return response;
		} catch (error) {
			lastError = error as Error;

			// Don't retry on abort or client errors
			if (error instanceof ApiError && error.status < 500) {
				throw error;
			}

			if (error instanceof DOMException && error.name === "AbortError") {
				lastError = new NetworkError("Request timed out");
			}

			// Wait before retrying (exponential backoff)
			if (attempt < retries) {
				await sleep(RETRY_DELAY * 2 ** attempt);
			}
		}
	}

	throw lastError || new NetworkError("Request failed after retries");
}

// =============================================================================
// API Client
// =============================================================================

function serializeDates(obj: Record<string, unknown>): Record<string, unknown> {
	const result: Record<string, unknown> = {};
	for (const [key, value] of Object.entries(obj)) {
		if (value instanceof Date) {
			result[key] = value.toISOString();
		} else if (value && typeof value === "object" && !Array.isArray(value)) {
			result[key] = serializeDates(value as Record<string, unknown>);
		} else {
			result[key] = value;
		}
	}
	return result;
}

function parseDates(obj: Record<string, unknown>): Record<string, unknown> {
	const dateFields = [
		"startTime",
		"endTime",
		"start",
		"end",
		"startDate",
		"endDate",
	];
	const result: Record<string, unknown> = {};

	for (const [key, value] of Object.entries(obj)) {
		if (dateFields.includes(key) && typeof value === "string") {
			result[key] = new Date(value);
		} else if (Array.isArray(value)) {
			result[key] = value.map((item) =>
				item && typeof item === "object"
					? parseDates(item as Record<string, unknown>)
					: item,
			);
		} else if (value && typeof value === "object") {
			result[key] = parseDates(value as Record<string, unknown>);
		} else {
			result[key] = value;
		}
	}

	return result;
}

export const api = {
	/**
	 * POST /api/chat - Send a chat message for discovery
	 */
	async chat(request: ChatRequest): Promise<ChatResponse> {
		const baseUrl = getBaseUrl();
		const response = await fetchWithRetry(`${baseUrl}/api/chat`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify(request),
		});

		const data = await response.json();
		return parseDates(data) as unknown as ChatResponse;
	},

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
						if (line.startsWith("data: ")) {
							try {
								const data = JSON.parse(line.slice(6)) as ChatStreamEvent;
								onChunk(data);
							} catch {
								// Skip malformed JSON
							}
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
	 * GET /api/events - Get event listings
	 */
	async getEvents(params?: EventsRequest): Promise<EventsResponse> {
		const baseUrl = getBaseUrl();
		const searchParams = new URLSearchParams();

		if (params) {
			const serialized = serializeDates(
				params as unknown as Record<string, unknown>,
			);
			for (const [key, value] of Object.entries(serialized)) {
				if (value !== undefined && value !== null) {
					searchParams.set(key, String(value));
				}
			}
		}

		const queryString = searchParams.toString();
		const url = `${baseUrl}/api/events${queryString ? `?${queryString}` : ""}`;

		const response = await fetchWithRetry(url, {
			method: "GET",
			headers: {
				"Content-Type": "application/json",
			},
		});

		const data = await response.json();
		return parseDates(data) as unknown as EventsResponse;
	},

	/**
	 * POST /api/search - Search events with filters
	 */
	async search(request: SearchRequest): Promise<SearchResponse> {
		const baseUrl = getBaseUrl();
		const serializedRequest = serializeDates(
			request as unknown as Record<string, unknown>,
		);

		const response = await fetchWithRetry(`${baseUrl}/api/search`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify(serializedRequest),
		});

		const data = await response.json();
		return parseDates(data) as unknown as SearchResponse;
	},

	/**
	 * POST /api/calendar/export - Export a single event as ICS file
	 */
	async exportEvent(event: CalendarEvent): Promise<void> {
		const baseUrl = getBaseUrl();
		const response = await fetch(`${baseUrl}/api/calendar/export`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({
				title: event.title,
				start: event.startTime.toISOString(),
				end: event.endTime?.toISOString(),
				description: event.description,
				location: event.location,
				url: event.url || event.sourceUrl,
			}),
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
		a.download = `${event.title.replace(/\s+/g, "-").toLowerCase()}.ics`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	},

	/**
	 * POST /api/calendar/export-multiple - Export multiple events as ICS file
	 */
	async exportEvents(events: CalendarEvent[]): Promise<void> {
		const baseUrl = getBaseUrl();
		const response = await fetch(`${baseUrl}/api/calendar/export-multiple`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
			},
			body: JSON.stringify({
				events: events.map((event) => ({
					title: event.title,
					start: event.startTime.toISOString(),
					end: event.endTime?.toISOString(),
					description: event.description,
					location: event.location,
					url: event.url || event.sourceUrl,
				})),
			}),
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
