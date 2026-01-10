"use client";

import posthog from "posthog-js";

let initialized = false;

/**
 * Initialize PostHog analytics
 * Call this once at app startup
 */
export function initPostHog(): void {
	if (typeof window === "undefined") return;
	if (initialized) return;

	const apiKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;
	if (!apiKey) {
		console.warn("[PostHog] NEXT_PUBLIC_POSTHOG_KEY not set");
		return;
	}

	posthog.init(apiKey, {
		api_host:
			process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
		person_profiles: "identified_only",
		capture_pageview: true,
		capture_pageleave: true,
		autocapture: true,
	});

	initialized = true;
}

/**
 * Track a chat message sent by the user
 */
export function trackChatMessage(data: {
	sessionId: string;
	messageLength: number;
}): void {
	if (!initialized) return;
	posthog.capture("chat_message_sent", {
		session_id: data.sessionId,
		message_length: data.messageLength,
	});
}

/**
 * Track when events are discovered/returned from search
 */
export function trackEventsDiscovered(data: {
	count: number;
	query?: string;
	latencyMs?: number;
}): void {
	if (!initialized) return;
	posthog.capture("events_discovered", {
		event_count: data.count,
		search_query: data.query,
		latency_ms: data.latencyMs,
	});
}

/**
 * Track calendar export action
 */
export function trackCalendarExport(data: {
	eventCount: number;
	exportType: "single" | "multiple";
}): void {
	if (!initialized) return;
	posthog.capture("calendar_exported", {
		event_count: data.eventCount,
		export_type: data.exportType,
	});
}

/**
 * Track when user clicks on an event to view details
 */
export function trackEventClicked(data: {
	eventId: string;
	eventTitle: string;
	category?: string;
}): void {
	if (!initialized) return;
	posthog.capture("event_clicked", {
		event_id: data.eventId,
		event_title: data.eventTitle,
		category: data.category,
	});
}

/**
 * Track page view (manual, for SPA navigation)
 */
export function trackPageView(path: string): void {
	if (!initialized) return;
	posthog.capture("$pageview", {
		$current_url: window.location.origin + path,
	});
}

/**
 * Identify a user (for logged-in users)
 */
export function identifyUser(
	userId: string,
	traits?: Record<string, unknown>,
): void {
	if (!initialized) return;
	posthog.identify(userId, traits);
}

/**
 * Reset user identity (on logout)
 */
export function resetUser(): void {
	if (!initialized) return;
	posthog.reset();
}

// Export the posthog instance for advanced usage
export { posthog };
