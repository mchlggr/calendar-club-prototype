"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
	api,
	type ChatRequest,
	type ChatResponse,
	type EventsRequest,
	type EventsResponse,
	type SearchRequest,
	type SearchResponse,
} from "./api";

// =============================================================================
// Query Keys
// =============================================================================

export const queryKeys = {
	events: {
		all: ["events"] as const,
		list: (params?: EventsRequest) =>
			[...queryKeys.events.all, "list", params] as const,
	},
	search: {
		all: ["search"] as const,
		results: (request: SearchRequest) =>
			[...queryKeys.search.all, "results", request] as const,
	},
	chat: {
		all: ["chat"] as const,
	},
};

// =============================================================================
// Events Hooks
// =============================================================================

/**
 * Fetch event listings
 */
export function useEvents(params?: EventsRequest) {
	return useQuery<EventsResponse>({
		queryKey: queryKeys.events.list(params),
		queryFn: () => api.getEvents(params),
	});
}

// =============================================================================
// Search Hooks
// =============================================================================

/**
 * Search for events with filters
 */
export function useSearch(
	request: SearchRequest,
	options?: { enabled?: boolean },
) {
	return useQuery<SearchResponse>({
		queryKey: queryKeys.search.results(request),
		queryFn: () => api.search(request),
		enabled: options?.enabled ?? !!request.query,
	});
}

/**
 * Search mutation for imperative search triggers
 */
export function useSearchMutation() {
	const queryClient = useQueryClient();

	return useMutation<SearchResponse, Error, SearchRequest>({
		mutationFn: (request) => api.search(request),
		onSuccess: (data, variables) => {
			// Cache the search results
			queryClient.setQueryData(queryKeys.search.results(variables), data);
		},
	});
}

// =============================================================================
// Chat Hooks
// =============================================================================

/**
 * Send a chat message
 */
export function useChatMutation() {
	return useMutation<ChatResponse, Error, ChatRequest>({
		mutationFn: (request) => api.chat(request),
	});
}

// =============================================================================
// Prefetch Utilities
// =============================================================================

/**
 * Prefetch events data (useful for route transitions)
 */
export function usePrefetchEvents() {
	const queryClient = useQueryClient();

	return (params?: EventsRequest) => {
		return queryClient.prefetchQuery({
			queryKey: queryKeys.events.list(params),
			queryFn: () => api.getEvents(params),
		});
	};
}

// =============================================================================
// Invalidation Utilities
// =============================================================================

/**
 * Invalidate all event queries
 */
export function useInvalidateEvents() {
	const queryClient = useQueryClient();

	return () => {
		return queryClient.invalidateQueries({ queryKey: queryKeys.events.all });
	};
}

/**
 * Invalidate all search queries
 */
export function useInvalidateSearch() {
	const queryClient = useQueryClient();

	return () => {
		return queryClient.invalidateQueries({ queryKey: queryKeys.search.all });
	};
}
