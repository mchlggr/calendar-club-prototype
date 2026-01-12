"use client";

import { Search } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useState } from "react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
	onSubmit: (query: string) => void;
	placeholder?: string;
	defaultValue?: string;
	disabled?: boolean;
	className?: string;
}

export function ChatInput({
	onSubmit,
	placeholder = "Find events and meetups, then download a calendar file for your week",
	defaultValue = "",
	disabled = false,
	className,
}: ChatInputProps) {
	const [value, setValue] = useState(defaultValue);

	const handleSubmit = (e: FormEvent) => {
		e.preventDefault();
		if (value.trim() && !disabled) {
			onSubmit(value.trim());
		}
	};

	const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			if (value.trim() && !disabled) {
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
				disabled={disabled}
				className={cn(
					"cc-input w-full px-4 py-4 pr-12",
					"placeholder:text-text-secondary",
					"focus:border-brand-green focus:outline-none focus:ring-1 focus:ring-brand-green",
					disabled && "cursor-not-allowed opacity-50",
				)}
			/>
			<button
				type="submit"
				disabled={disabled}
				className={cn(
					"btn-brutal cc-btn-icon absolute right-3 top-1/2 -translate-y-1/2 transition-colors hover:bg-bg-cream hover:text-brand-green",
					disabled && "cursor-not-allowed opacity-50",
				)}
				aria-label="Search"
			>
				<Search className="h-5 w-5" aria-hidden="true" />
			</button>
		</form>
	);
}
