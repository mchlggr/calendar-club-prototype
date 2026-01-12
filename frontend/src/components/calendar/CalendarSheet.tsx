"use client";

import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { CalendarEvent } from "./types";
import { WeekView } from "./WeekView";

function getWeekStart(date: Date): Date {
	const d = new Date(date);
	const day = d.getDay();
	d.setDate(d.getDate() - day);
	d.setHours(0, 0, 0, 0);
	return d;
}

export function CalendarSheet() {
	const router = useRouter();
	const [events, setEvents] = useState<CalendarEvent[]>([]);
	const [weekStart, setWeekStart] = useState(() => getWeekStart(new Date()));

	// Load events from sessionStorage
	useEffect(() => {
		const stored = sessionStorage.getItem("discoveredEvents");
		if (stored) {
			try {
				const parsed = JSON.parse(stored);
				const loadedEvents = parsed.map(
					(e: Record<string, unknown>): CalendarEvent => {
						const startTime = new Date(e.startTime as string);
						const endTime = e.endTime
							? new Date(e.endTime as string)
							: new Date(startTime.getTime() + 2 * 60 * 60 * 1000);
						return {
							...e,
							startTime,
							endTime,
						} as CalendarEvent;
					},
				);
				setEvents(loadedEvents);

				// Auto-navigate to the week containing the first event
				if (loadedEvents.length > 0) {
					const firstEventDate = loadedEvents.reduce(
						(earliest: Date, event: CalendarEvent) =>
							event.startTime < earliest ? event.startTime : earliest,
						loadedEvents[0].startTime,
					);
					setWeekStart(getWeekStart(firstEventDate));
				}
			} catch (error) {
				console.error("Failed to parse stored events:", error);
			}
		}
	}, []);

	const handleClose = useCallback(() => {
		router.back();
	}, [router]);

	const handlePrevWeek = () => {
		const prev = new Date(weekStart);
		prev.setDate(prev.getDate() - 7);
		setWeekStart(prev);
	};

	const handleNextWeek = () => {
		const next = new Date(weekStart);
		next.setDate(next.getDate() + 7);
		setWeekStart(next);
	};

	const handleEventClick = (event: CalendarEvent) => {
		if (event.canonicalUrl) {
			window.open(event.canonicalUrl, "_blank");
		}
	};

	// Close on Escape key
	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.key === "Escape") handleClose();
		};
		document.addEventListener("keydown", handleKeyDown);
		return () => document.removeEventListener("keydown", handleKeyDown);
	}, [handleClose]);

	return (
		<>
			{/* Backdrop */}
			<motion.div
				initial={{ opacity: 0 }}
				animate={{ opacity: 1 }}
				exit={{ opacity: 0 }}
				transition={{ duration: 0.2 }}
				className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
				onClick={handleClose}
			/>

			{/* Sheet */}
			<motion.div
				initial={{ y: "100%" }}
				animate={{ y: 0 }}
				exit={{ y: "100%" }}
				transition={{ type: "spring", damping: 30, stiffness: 300 }}
				className="fixed inset-x-0 bottom-0 z-50 flex h-[85vh] flex-col rounded-t-2xl bg-bg-cream shadow-2xl"
				onClick={(e) => e.stopPropagation()}
			>
				{/* Handle bar */}
				<div className="flex justify-center py-2">
					<div className="h-1.5 w-12 rounded-full bg-gray-300" />
				</div>

				{/* Header */}
				<div className="flex items-center justify-between border-b border-border-light px-4 pb-3">
					<div className="flex items-center gap-2">
						<button
							type="button"
							onClick={handlePrevWeek}
							className="rounded-full p-2 hover:bg-gray-100"
							aria-label="Previous week"
						>
							<ChevronLeft className="h-5 w-5" />
						</button>
						<button
							type="button"
							onClick={handleNextWeek}
							className="rounded-full p-2 hover:bg-gray-100"
							aria-label="Next week"
						>
							<ChevronRight className="h-5 w-5" />
						</button>
					</div>

					<div className="flex items-center gap-2">
						<button
							type="button"
							className="flex items-center gap-1 rounded-lg bg-brand-green px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-green/90"
						>
							<Download className="h-4 w-4" />
							Export .ics
						</button>
						<button
							type="button"
							onClick={handleClose}
							className="rounded-full p-2 hover:bg-gray-100"
							aria-label="Close"
						>
							<X className="h-5 w-5" />
						</button>
					</div>
				</div>

				{/* Calendar content */}
				<div className="flex-1 overflow-y-auto p-4">
					<WeekView
						events={events}
						weekStart={weekStart}
						onEventClick={handleEventClick}
					/>
				</div>
			</motion.div>
		</>
	);
}
