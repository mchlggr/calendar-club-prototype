"use client";

import { Search } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useState } from "react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
	onSubmit: (query: string) => void;
	placeholder?: string;
	defaultValue?: string;
	className?: string;
}

export function ChatInput({
	onSubmit,
	placeholder = "Search events...",
	defaultValue = "",
	className,
}: ChatInputProps) {
	const [value, setValue] = useState(defaultValue);

	const handleSubmit = (e: FormEvent) => {
		e.preventDefault();
		if (value.trim()) {
			onSubmit(value.trim());
		}
	};

	const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			if (value.trim()) {
				onSubmit(value.trim());
			}
		}
	};

	return (
		<form onSubmit={handleSubmit} className={cn("relative w-full", className)}>
			<input
				type="text"
				value={value}
				onChange={(e) => setValue(e.target.value)}
				onKeyDown={handleKeyDown}
				placeholder={placeholder}
				className={cn(
					"cc-input w-full px-4 py-4 pr-12",
					"placeholder:text-text-secondary",
					"focus:border-brand-green focus:outline-none focus:ring-1 focus:ring-brand-green",
				)}
			/>
			<button
				type="submit"
				className="btn-brutal cc-btn-icon absolute right-3 top-1/2 -translate-y-1/2 transition-colors hover:bg-bg-cream hover:text-brand-green"
				aria-label="Search"
			>
				<Search className="h-5 w-5" aria-hidden="true" />
			</button>
		</form>
	);
}
