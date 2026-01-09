"use client";

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { cn, cssVars, deterministicRotationDeg } from "@/lib/utils";

interface PromoBannerProps {
	className?: string;
	storageKey?: string;
}

export function PromoBanner({
	className,
	storageKey = "cc_promo_dismissed_v1",
}: PromoBannerProps) {
	const [isDismissed, setIsDismissed] = useState(false);

	useEffect(() => {
		try {
			setIsDismissed(window.localStorage.getItem(storageKey) === "1");
		} catch {
			// Ignore storage errors (e.g. private mode)
		}
	}, [storageKey]);

	const rotationDeg = useMemo(
		() =>
			deterministicRotationDeg(storageKey, {
				min: -1.5,
				max: 1.5,
				step: 0.5,
			}),
		[storageKey],
	);

	if (isDismissed) return null;

	const handleDismiss = () => {
		setIsDismissed(true);
		try {
			window.localStorage.setItem(storageKey, "1");
		} catch {
			// Ignore storage errors
		}
	};

	return (
		<div className={cn("w-full px-6 pt-4 md:px-12", className)}>
			<section
				className="paper-card relative flex w-full items-start justify-between gap-4 p-4 tape-accent md:items-center"
				style={{
					...cssVars({ "--cc-rotate": `${rotationDeg}deg` }),
					backgroundColor: "var(--color-accent-yellow)",
				}}
				aria-label="Promotion"
			>
				<div className="tape cc-tape-left absolute -top-3 left-6 h-6 w-16 rotate-[-6deg]" />
				<div className="tape cc-tape-right absolute -top-3 right-6 h-6 w-16 rotate-[8deg]" />

				<div className="min-w-0 cc-inset-grid p-2">
					<div className="cc-label text-text-primary">New</div>
					<div className="mt-1 cc-h3 text-text-primary">
						Get the weekly signal
					</div>
					<p className="mt-1 max-w-xl cc-body-sm text-text-secondary">
						A Sunday drop of the best technical meetups—no noise, just deep
						cuts.
					</p>
				</div>

				<div className="flex shrink-0 items-center gap-2">
					<a href="/subscribe" className="btn-brutal cc-btn-primary">
						Subscribe
					</a>
					<button
						type="button"
						onClick={handleDismiss}
						className="btn-brutal cc-btn-icon"
						aria-label="Dismiss promotion"
					>
						<X className="h-4 w-4" aria-hidden="true" />
					</button>
				</div>
			</section>
		</div>
	);
}
