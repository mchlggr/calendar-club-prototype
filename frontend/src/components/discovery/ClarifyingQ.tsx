"use client";

/**
 * @deprecated This component is deprecated in favor of LLM-driven quick picks.
 * The DiscoveryChat component now uses QuickPicks with dynamic options from the
 * chat stream instead of the static question flow provided by ClarifyingQ.
 * This file is kept for reference but should not be used in new code.
 */

import { cn } from "@/lib/utils";

/**
 * @deprecated Use QuickPickOption from @/lib/api instead.
 */
export type QuestionType = "time" | "category" | "location" | "cost";

interface ChipOption {
	label: string;
	value: string;
}

interface ClarifyingQProps {
	questionType: QuestionType;
	onAnswer: (value: string, method: "chip" | "text") => void;
	className?: string;
}

const questionConfig: Record<
	QuestionType,
	{ question: string; chips: ChipOption[] }
> = {
	time: {
		question: "When are you looking?",
		chips: [
			{ label: "Today", value: "today" },
			{ label: "This weekend", value: "this-weekend" },
			{ label: "Next week", value: "next-week" },
			{ label: "Pick dates", value: "pick-dates" },
		],
	},
	category: {
		question: "What kind of events?",
		chips: [
			{ label: "AI/Tech", value: "ai-tech" },
			{ label: "Startups", value: "startups" },
			{ label: "Community", value: "community" },
			{ label: "All of the above", value: "all" },
		],
	},
	location: {
		question: "How far will you go?",
		chips: [
			{ label: "Downtown only", value: "downtown" },
			{ label: "Within 15 min", value: "15-min" },
			{ label: "Anywhere in Columbus", value: "anywhere" },
		],
	},
	cost: {
		question: "Free, paid, or both?",
		chips: [
			{ label: "Free only", value: "free" },
			{ label: "Any price", value: "any" },
		],
	},
};

/**
 * @deprecated Use QuickPicks component with LLM-driven options instead.
 */
export function ClarifyingQ({
	questionType,
	onAnswer,
	className,
}: ClarifyingQProps) {
	const config = questionConfig[questionType];

	const handleChipClick = (value: string) => {
		onAnswer(value, "chip");
	};

	return (
		<div className={cn("flex flex-col gap-3", className)}>
			{/* Agent message bubble */}
			<div className="flex items-start gap-3">
				{/* Agent avatar */}
				<div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-green">
					<span className="text-xs font-semibold text-white">CC</span>
				</div>

				{/* Message bubble */}
				<div className="max-w-md rounded-lg border-l-[3px] border-brand-green bg-bg-white px-4 py-3 shadow-sm">
					<p className="text-sm font-medium text-text-primary">
						{config.question}
					</p>
				</div>
			</div>

			{/* Chip options */}
			<div className="ml-11 flex flex-wrap gap-2">
				{config.chips.map((chip) => (
					<button
						key={chip.value}
						type="button"
						onClick={() => handleChipClick(chip.value)}
						className="rounded-2xl bg-bg-cream px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:bg-accent-yellow"
					>
						{chip.label}
					</button>
				))}
			</div>
		</div>
	);
}
