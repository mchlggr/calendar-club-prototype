"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import type { CalendarEvent } from "@/components/calendar";
import { api } from "@/lib/api";
import { trackCalendarExport, trackEventClicked } from "@/lib/posthog";
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
	const [isExporting, setIsExporting] = useState(false);
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
		try {
			// Map CalendarEvent from calendar component to api CalendarEvent type
			await api.exportEvents(
				events.map((e) => ({
					id: e.id,
					title: e.title,
					startTime: e.startTime,
					endTime: e.endTime,
					location: e.venue,
					source: e.sourceId,
					sourceUrl: e.canonicalUrl,
				})),
			);
			// Track successful export
			trackCalendarExport({
				eventCount: events.length,
				exportType: events.length === 1 ? "single" : "multiple",
			});
		} catch (error) {
			console.error("Export failed:", error);
		} finally {
			setIsExporting(false);
		}
	};

	return (
		<div className={cn("flex flex-col gap-4", className)}>
			{/* Agent message */}
			<div className="flex items-start gap-3">
				<div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-green">
					<span className="text-xs font-semibold text-white">CC</span>
				</div>
				<div className="rounded-lg border-l-[3px] border-brand-green bg-bg-white px-4 py-3 shadow-sm">
					<p className="text-sm font-medium text-text-primary">
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
						className="flex items-center gap-3 rounded-lg border border-border-light bg-bg-white p-3 text-left transition-colors hover:bg-bg-cream"
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
							<h4 className="truncate text-sm font-medium text-text-primary">
								{event.title}
							</h4>
							<p className="text-xs text-text-secondary">
								{formatEventDate(event.startTime)} at{" "}
								{formatEventTime(event.startTime)}
								{event.venue && ` · ${event.venue}`}
							</p>
						</div>
					</button>
				))}

				{totalCount > 5 && (
					<p className="text-xs text-text-secondary">
						+{totalCount - 5} more events
					</p>
				)}
			</div>

			{/* Action buttons */}
			<div className="ml-11 flex flex-wrap gap-3">
				<button
					type="button"
					onClick={onViewWeek}
					className="rounded-lg bg-brand-green px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-green/90"
				>
					View full week
				</button>
				<button
					type="button"
					onClick={handleExportAll}
					disabled={isExporting || events.length === 0}
					className="flex items-center gap-2 rounded-lg border border-border-light bg-bg-white px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-cream disabled:cursor-not-allowed disabled:opacity-50"
				>
					<Download className="h-4 w-4" />
					{isExporting ? "Exporting..." : "Add all to calendar"}
				</button>
				{onRefine && (
					<button
						type="button"
						onClick={onRefine}
						className="rounded-lg border border-border-light bg-bg-white px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-bg-cream"
					>
						Narrow it down
					</button>
				)}
			</div>
		</div>
	);
}
