"use client";

import { cn } from "@/lib/utils";

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
				<div className="cc-avatar shrink-0">
					<span className="cc-avatar-text">CC</span>
				</div>

				{/* Message bubble */}
				<div className="cc-bubble cc-bubble-agent max-w-md">
					<p className="cc-body font-medium">{config.question}</p>
				</div>
			</div>

			{/* Chip options */}
			<div className="ml-11 flex flex-wrap gap-2">
				{config.chips.map((chip) => (
					<button
						key={chip.value}
						type="button"
						onClick={() => handleChipClick(chip.value)}
						className="cc-chip"
					>
						{chip.label}
					</button>
				))}
			</div>
		</div>
	);
}
