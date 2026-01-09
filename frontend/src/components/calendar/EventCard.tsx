"use client";

import { cn } from "@/lib/utils";
import type { CalendarEvent, EventCategory } from "./types";

interface EventCardProps {
	event: CalendarEvent;
	onClick?: (event: CalendarEvent) => void;
	onHover?: (event: CalendarEvent | null, element?: HTMLElement) => void;
	className?: string;
}

const categoryStyles: Record<EventCategory, string> = {
	meetup: "category-meetup",
	startup: "category-startup",
	community: "category-community",
	ai: "category-ai",
};

const categoryBadgeStyles: Record<EventCategory, string> = {
	meetup: "bg-category-meetup text-white",
	startup: "bg-category-startup text-white",
	community: "bg-brand-green text-white",
	ai: "bg-category-aitech text-white",
};

function formatTime(date: Date): string {
	const hours = date.getHours();
	const ampm = hours >= 12 ? "PM" : "AM";
	const hour12 = hours % 12 || 12;
	return `${hour12}${ampm}`;
}

export function EventCard({
	event,
	onClick,
	onHover,
	className,
}: EventCardProps) {
	const handleClick = () => {
		onClick?.(event);
		if (event.canonicalUrl) {
			window.open(event.canonicalUrl, "_blank", "noopener,noreferrer");
		}
	};

	return (
		<button
			type="button"
			className={cn(
				"group w-full cursor-pointer rounded-lg border border-border-light bg-bg-white p-2 text-left shadow-sm transition-all",
				"hover:-translate-y-0.5 hover:shadow-md",
				categoryStyles[event.category],
				className,
			)}
			onClick={handleClick}
			onMouseEnter={(e) => onHover?.(event, e.currentTarget)}
			onMouseLeave={() => onHover?.(null)}
		>
			{/* Category badge for meetups */}
			{event.category === "meetup" && (
				<span
					className={cn(
						"mb-1 inline-block rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
						categoryBadgeStyles[event.category],
					)}
				>
					Meetup
				</span>
			)}

			{/* Time */}
			<time className="font-jetbrains block text-xs text-text-secondary">
				{formatTime(event.startTime)}
			</time>

			{/* Title */}
			<h3 className="mt-0.5 line-clamp-2 text-[13px] font-medium text-text-primary">
				{event.title}
			</h3>
		</button>
	);
}
