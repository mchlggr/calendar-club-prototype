"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function QueryProvider({ children }: { children: React.ReactNode }) {
	const [queryClient] = useState(
		() =>
			new QueryClient({
				defaultOptions: {
					queries: {
						// Stale time of 5 minutes for event data
						staleTime: 5 * 60 * 1000,
						// Cache for 30 minutes
						gcTime: 30 * 60 * 1000,
						// Retry failed requests up to 3 times
						retry: 3,
						// Exponential backoff for retries
						retryDelay: (attemptIndex) =>
							Math.min(1000 * 2 ** attemptIndex, 30000),
					},
					mutations: {
						// Retry mutations once
						retry: 1,
					},
				},
			}),
	);

	return (
		<QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
	);
}
