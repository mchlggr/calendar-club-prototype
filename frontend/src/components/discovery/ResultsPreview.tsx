"use client";

import { Download } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import { api } from "@/lib/api";
import { trackCalendarExport, trackEventClicked } from "@/lib/posthog";
import { cn } from "@/lib/utils";

interface ResultsPreviewProps {
	events: CalendarEvent[];
	totalCount: number;
	onViewWeek: () => void;
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
	onEventClick,
	className,
}: ResultsPreviewProps) {
	const [isExporting, setIsExporting] = useState(false);
	const [exportError, setExportError] = useState<string | null>(null);
	const displayEvents = events.slice(0, 5);

	const handleEventClick = (event: CalendarEvent) => {
		// Track event click
		trackEventClicked({
			eventId: event.id,
			eventTitle: event.title,
			category: event.category,
		});
		onEventClick?.(event);
		if (event.canonicalUrl) {
			window.open(event.canonicalUrl, "_blank", "noopener,noreferrer");
		}
	};

	const handleExportAll = async () => {
		if (events.length === 0) return;
		setIsExporting(true);
		setExportError(null);
		try {
			await api.exportEvents(
				events.map((e) => ({
					title: e.title,
					start: e.startTime.toISOString(),
					end: e.endTime?.toISOString(),
					location: e.venue,
					url: e.canonicalUrl || undefined,
				})),
			);
			// Track successful export
			trackCalendarExport({
				eventCount: events.length,
				exportType: events.length === 1 ? "single" : "multiple",
			});
		} catch (error) {
			console.error("Export failed:", error);
			setExportError("Couldn't generate a calendar file. Please try again.");
		} finally {
			setIsExporting(false);
		}
	};

	return (
		<div className={cn("flex flex-col gap-4", className)}>
			{/* Compact event cards */}
			<div className="flex flex-col gap-2">
				{displayEvents.map((event) => {
					const cardContent = (
						<>
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
						</>
					);

					if (!event.canonicalUrl) {
						return (
							<div
								key={event.id}
								className="paper-card flex items-center gap-3 p-3 text-left"
							>
								{cardContent}
							</div>
						);
					}

					return (
						<button
							key={event.id}
							type="button"
							onClick={() => handleEventClick(event)}
							className="paper-card flex items-center gap-3 p-3 text-left transition-colors hover:bg-bg-cream"
						>
							{cardContent}
						</button>
					);
				})}

				{totalCount > 5 && (
					<p className="cc-body-sm text-text-secondary">
						+{totalCount - 5} more events
					</p>
				)}
			</div>

			{/* Action buttons */}
			<div className="flex flex-wrap gap-3">
				<Link
					href="/week"
					onClick={onViewWeek}
					className="btn-brutal cc-btn-primary"
				>
					View full week
				</Link>
				<button
					type="button"
					onClick={handleExportAll}
					disabled={isExporting || events.length === 0}
					className="flex items-center gap-2 rounded-lg border border-border-light bg-bg-white px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-cream disabled:cursor-not-allowed disabled:opacity-50"
				>
					<Download className="h-4 w-4" />
					{isExporting ? "Exporting..." : "Download .ics"}
				</button>
			</div>

			{exportError && (
				<p className="text-sm text-text-secondary" role="alert">
					{exportError}
				</p>
			)}
		</div>
	);
}
