"use client";

import type { CalendarEvent } from "@/components/calendar";
import { cn } from "@/lib/utils";

interface ResultsPreviewProps {
	events: CalendarEvent[];
	totalCount: number;
	onViewWeek: () => void;
	onRefine?: () => void;
	onEventClick?: (event: CalendarEvent) => void;
	className?: string;
}

function formatEventTime(date: Date): string {
	const hours = date.getHours();
	const minutes = date.getMinutes();
	const ampm = hours >= 12 ? "PM" : "AM";
	const hour12 = hours % 12 || 12;
	return minutes
		? `${hour12}:${minutes.toString().padStart(2, "0")} ${ampm}`
		: `${hour12} ${ampm}`;
}

function formatEventDate(date: Date): string {
	return date.toLocaleDateString("en-US", {
		weekday: "short",
		month: "short",
		day: "numeric",
	});
}

const categoryColors: Record<CalendarEvent["category"], string> = {
	meetup: "bg-accent-orange",
	startup: "bg-brand-green",
	community: "bg-accent-teal",
	ai: "bg-accent-blue",
};

export function ResultsPreview({
	events,
	totalCount,
	onViewWeek,
	onRefine,
	onEventClick,
	className,
}: ResultsPreviewProps) {
	const displayEvents = events.slice(0, 5);

	const handleEventClick = (event: CalendarEvent) => {
		onEventClick?.(event);
		if (event.canonicalUrl) {
			window.open(event.canonicalUrl, "_blank", "noopener,noreferrer");
		}
	};

	return (
		<div className={cn("flex flex-col gap-4", className)}>
			{/* Agent message */}
			<div className="flex items-start gap-3">
				<div className="cc-avatar shrink-0">
					<span className="cc-avatar-text">CC</span>
				</div>
				<div className="cc-bubble cc-bubble-agent">
					<p className="cc-body font-medium">
						I found {totalCount} events that match...
					</p>
				</div>
			</div>

			{/* Compact event cards */}
			<div className="ml-11 flex flex-col gap-2">
				{displayEvents.map((event) => (
					<button
						key={event.id}
						type="button"
						onClick={() => handleEventClick(event)}
						className="paper-card flex items-center gap-3 p-3 text-left transition-colors hover:bg-bg-cream"
					>
						{/* Category indicator */}
						<div
							className={cn(
								"h-10 w-1 shrink-0 rounded-full",
								categoryColors[event.category],
							)}
						/>

						{/* Event info */}
						<div className="min-w-0 flex-1">
							<h4 className="truncate cc-body font-medium">{event.title}</h4>
							<p className="cc-body-sm text-text-secondary">
								{formatEventDate(event.startTime)} at{" "}
								{formatEventTime(event.startTime)}
								{event.venue && ` · ${event.venue}`}
							</p>
						</div>
					</button>
				))}

				{totalCount > 5 && (
					<p className="cc-body-sm text-text-secondary">
						+{totalCount - 5} more events
					</p>
				)}
			</div>

			{/* Action buttons */}
			<div className="ml-11 flex flex-wrap gap-3">
				<button
					type="button"
					onClick={onViewWeek}
					className="btn-brutal cc-btn-primary"
				>
					View full week
				</button>
				{onRefine && (
					<button
						type="button"
						onClick={onRefine}
						className="btn-brutal cc-btn-secondary hover:bg-bg-cream"
					>
						Narrow it down
					</button>
				)}
			</div>
		</div>
	);
}
