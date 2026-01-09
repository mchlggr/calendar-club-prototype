import { type ClassValue, clsx } from "clsx";
import type { CSSProperties } from "react";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export function cssVars(
	vars: Record<`--${string}`, string | number>,
): CSSProperties {
	return vars as unknown as CSSProperties;
}

export function hashStringToUint32(input: string): number {
	let hash = 2166136261;
	for (let i = 0; i < input.length; i += 1) {
		hash ^= input.charCodeAt(i);
		hash = Math.imul(hash, 16777619);
	}
	return hash >>> 0;
}

export function deterministicRotationDeg(
	key: string,
	options?: {
		min?: number;
		max?: number;
		step?: number;
	},
): number {
	const min = options?.min ?? -2;
	const max = options?.max ?? 2;
	const step = options?.step ?? 0.5;

	if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return 0;
	if (!Number.isFinite(step) || step <= 0) {
		const t = hashStringToUint32(key) / 0xffffffff;
		return min + t * (max - min);
	}

	const count = Math.max(1, Math.round((max - min) / step));
	const idx = hashStringToUint32(key) % (count + 1);
	return min + idx * step;
}
