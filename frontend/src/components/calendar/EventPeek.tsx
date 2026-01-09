"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { CalendarEvent } from "./types";

interface EventPeekProps {
	event: CalendarEvent | null;
	anchorRect?: DOMRect | null;
	className?: string;
}

const HOVER_DELAY_MS = 300;

export function EventPeek({ event, anchorRect, className }: EventPeekProps) {
	const [isVisible, setIsVisible] = useState(false);
	const [debouncedEvent, setDebouncedEvent] = useState<CalendarEvent | null>(
		null,
	);
	const timeoutRef = useRef<NodeJS.Timeout | null>(null);
	const peekRef = useRef<HTMLDivElement>(null);

	// Debounced visibility with 300ms delay
	useEffect(() => {
		if (event) {
			timeoutRef.current = setTimeout(() => {
				setDebouncedEvent(event);
				setIsVisible(true);

				// Telemetry: calendar:event_hover
				if (typeof window !== "undefined") {
					window.dispatchEvent(
						new CustomEvent("calendar:event_hover", {
							detail: { eventId: event.id, eventTitle: event.title },
						}),
					);
				}
			}, HOVER_DELAY_MS);
		} else {
			setIsVisible(false);
			setDebouncedEvent(null);
		}

		return () => {
			if (timeoutRef.current) {
				clearTimeout(timeoutRef.current);
			}
		};
	}, [event]);

	// Calculate position relative to anchor
	const getPosition = () => {
		if (!anchorRect) {
			return { top: 0, left: 0 };
		}

		// Position below and slightly to the right of the card
		return {
			top: anchorRect.bottom + 8,
			left: anchorRect.left,
		};
	};

	if (!isVisible || !debouncedEvent) {
		return null;
	}

	const position = getPosition();
	const hasVenue = debouncedEvent.venue;
	const hasNeighborhood = debouncedEvent.neighborhood;
	const hasDetails = hasVenue || hasNeighborhood;

	return (
		<div
			ref={peekRef}
			role="tooltip"
			className={cn(
				"paper-card fixed z-50 min-w-[200px] max-w-[280px] p-3",
				"animate-in fade-in-0 zoom-in-95 duration-150",
				className,
			)}
			style={{
				top: position.top,
				left: position.left,
			}}
		>
			{/* Venue */}
			{hasVenue && (
				<div className="mb-1.5">
					<span className="text-[11px] font-medium uppercase tracking-wide text-text-secondary">
						Venue
					</span>
					<p className="text-[13px] text-text-primary">
						{debouncedEvent.venue}
					</p>
				</div>
			)}

			{/* Neighborhood */}
			{hasNeighborhood && (
				<div className="mb-1.5">
					<span className="text-[11px] font-medium uppercase tracking-wide text-text-secondary">
						Neighborhood
					</span>
					<p className="text-[13px] text-text-primary">
						{debouncedEvent.neighborhood}
					</p>
				</div>
			)}

			{/* No details fallback */}
			{!hasDetails && (
				<p className="text-[12px] text-text-secondary italic">
					No location details available
				</p>
			)}

			{/* RSVP Link */}
			{debouncedEvent.canonicalUrl && (
				<a
					href={debouncedEvent.canonicalUrl}
					target="_blank"
					rel="noopener noreferrer"
					className={cn(
						"mt-2 inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[12px] font-medium",
						"bg-brand-green/10 text-brand-green hover:bg-brand-green/20",
						"transition-colors duration-150",
					)}
					onClick={(e) => e.stopPropagation()}
				>
					RSVP
					<svg
						aria-hidden="true"
						className="h-3 w-3"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
					>
						<path
							strokeLinecap="round"
							strokeLinejoin="round"
							strokeWidth={2}
							d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
						/>
					</svg>
				</a>
			)}
		</div>
	);
}
