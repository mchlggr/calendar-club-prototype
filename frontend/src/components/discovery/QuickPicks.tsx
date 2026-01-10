"use client";

import type { QuickPickOption } from "@/lib/api";
import { cn } from "@/lib/utils";

interface QuickPicksProps {
	options?: QuickPickOption[];
	onSelect: (value: string) => void;
	selectedValues?: string[];
	className?: string;
}

const defaultOptions: QuickPickOption[] = [
	{ label: "This weekend", value: "I'm looking for events this weekend" },
	{ label: "AI/Tech", value: "I want to find AI and tech events" },
	{ label: "Startups", value: "Show me startup and founder events" },
	{ label: "Free events", value: "I'm looking for free events" },
];

export function QuickPicks({
	options = defaultOptions,
	onSelect,
	selectedValues = [],
	className,
}: QuickPicksProps) {
	return (
		<div className={cn("flex flex-wrap gap-2", className)}>
			{options.map((option) => {
				const isSelected = selectedValues.includes(option.value);
				return (
					<button
						key={option.value}
						type="button"
						onClick={() => onSelect(option.value)}
						className={cn(
							"rounded-2xl px-4 py-2 text-sm font-medium transition-colors",
							isSelected
								? "bg-accent-yellow text-text-primary"
								: "bg-bg-cream text-text-primary hover:bg-accent-yellow",
						)}
					>
						{option.label}
					</button>
				);
			})}
		</div>
	);
}
