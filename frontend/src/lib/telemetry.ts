"use client";

import HyperDX from "@hyperdx/browser";

const SESSION_ID_KEY = "cc_session_id";
const CLICK_OUT_TIME_KEY = "cc_last_click_out";

// Session UUID management - persists across visits
export const getSessionId = (): string => {
	if (typeof window === "undefined") return "";

	let id = localStorage.getItem(SESSION_ID_KEY);
	if (!id) {
		id = crypto.randomUUID();
		localStorage.setItem(SESSION_ID_KEY, id);
	}
	return id;
};

// Initialize HyperDX telemetry
export const initTelemetry = () => {
	if (typeof window === "undefined") return;

	const apiKey = process.env.NEXT_PUBLIC_HYPERDX_API_KEY;
	if (!apiKey) {
		console.warn("[Telemetry] NEXT_PUBLIC_HYPERDX_API_KEY not set");
		return;
	}

	const endpoint = process.env.NEXT_PUBLIC_HYPERDX_ENDPOINT;

	HyperDX.init({
		apiKey,
		service: "calendarclub-frontend",
		tracePropagationTargets: [/api\./, /localhost/i],
		consoleCapture: true,
		advancedNetworkCapture: false,
		...(endpoint && { url: endpoint }),
	});

	// Set session ID as global attribute
	HyperDX.setGlobalAttributes({
		sessionId: getSessionId(),
	});
};

// Event type definitions
interface SearchPerformedEvent {
	query: string;
	parsedIntent?: string;
	chipsUsed?: string[];
}

interface ClarificationAnsweredEvent {
	questionType: string;
	answer: string;
	method: "click" | "voice" | "type";
}

interface ResultsViewedEvent {
	count: number;
	latencyMs: number;
	from: "search" | "filter" | "navigation";
}

interface EventClickedOutEvent {
	eventId: string;
	source: string;
	category?: string;
}

interface EventHoverEvent {
	eventId: string;
	dayOfWeek: number;
}

interface BoomerangReturnEvent {
	timeSinceClickOutMs: number;
	eventId?: string;
}

interface FeedbackRatedEvent {
	rating: number;
	eventId: string;
}

// Event tracking functions
export const trackSearchPerformed = (data: SearchPerformedEvent) => {
	HyperDX.addAction("search_performed", {
		query: data.query,
		parsed_intent: data.parsedIntent,
		chips_used: data.chipsUsed?.join(","),
	});
};

export const trackClarificationAnswered = (
	data: ClarificationAnsweredEvent,
) => {
	HyperDX.addAction("clarification_answered", {
		question_type: data.questionType,
		answer: data.answer,
		method: data.method,
	});
};

export const trackResultsViewed = (data: ResultsViewedEvent) => {
	HyperDX.addAction("results_viewed", {
		count: data.count.toString(),
		latency_ms: data.latencyMs.toString(),
		from: data.from,
	});
};

export const trackEventClickedOut = (data: EventClickedOutEvent) => {
	// Store click-out time for boomerang tracking
	if (typeof window !== "undefined") {
		localStorage.setItem(
			CLICK_OUT_TIME_KEY,
			JSON.stringify({
				time: Date.now(),
				eventId: data.eventId,
			}),
		);
	}

	HyperDX.addAction("event_clicked_out", {
		event_id: data.eventId,
		source: data.source,
		category: data.category,
	});
};

export const trackEventHover = (data: EventHoverEvent) => {
	HyperDX.addAction("calendar:event_hover", {
		event_id: data.eventId,
		day_of_week: data.dayOfWeek.toString(),
	});
};

export const trackBoomerangReturn = (data?: Partial<BoomerangReturnEvent>) => {
	if (typeof window === "undefined") return;

	// Check for previous click-out
	const stored = localStorage.getItem(CLICK_OUT_TIME_KEY);
	if (!stored) return;

	try {
		const { time, eventId } = JSON.parse(stored);
		const timeSinceClickOutMs = Date.now() - time;

		HyperDX.addAction("boomerang_return", {
			time_since_click_out_ms: timeSinceClickOutMs.toString(),
			event_id: data?.eventId ?? eventId,
		});

		// Clear the stored click-out
		localStorage.removeItem(CLICK_OUT_TIME_KEY);
	} catch {
		// Invalid stored data, clear it
		localStorage.removeItem(CLICK_OUT_TIME_KEY);
	}
};

export const trackFeedbackRated = (data: FeedbackRatedEvent) => {
	HyperDX.addAction("feedback_rated", {
		rating: data.rating.toString(),
		event_id: data.eventId,
	});
};

// Export the HyperDX instance for advanced usage
export { HyperDX };
