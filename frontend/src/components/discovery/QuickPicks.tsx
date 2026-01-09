"use client";

import { cn } from "@/lib/utils";

interface QuickPickOption {
	label: string;
	value: string;
}

interface QuickPicksProps {
	options?: QuickPickOption[];
	onSelect: (value: string) => void;
	selectedValues?: string[];
	className?: string;
}

const defaultOptions: QuickPickOption[] = [
	{ label: "This weekend", value: "this-weekend" },
	{ label: "AI/Tech", value: "ai-tech" },
	{ label: "Startups", value: "startups" },
	{ label: "Free events", value: "free" },
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
						className={cn("cc-chip", isSelected && "cc-chip-selected")}
					>
						{option.label}
					</button>
				);
			})}
		</div>
	);
}
