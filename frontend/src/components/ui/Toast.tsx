"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

export type ToastType = "success" | "error" | "info" | "warning";

interface ToastProps {
	message: string;
	type?: ToastType;
	duration?: number;
	onClose?: () => void;
}

const typeStyles: Record<ToastType, string> = {
	success: "border-brand-green bg-brand-green/10 text-brand-green",
	error: "border-recording-red bg-recording-red/10 text-recording-red",
	info: "border-category-aitech bg-category-aitech/10 text-category-aitech",
	warning: "border-category-meetup bg-category-meetup/10 text-category-meetup",
};

const typeIcons: Record<ToastType, string> = {
	success: "M5 13l4 4L19 7",
	error: "M6 18L18 6M6 6l12 12",
	info: "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
	warning:
		"M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z",
};

export function Toast({
	message,
	type = "info",
	duration = 5000,
	onClose,
}: ToastProps) {
	const [isVisible, setIsVisible] = useState(true);

	useEffect(() => {
		if (duration > 0) {
			const timer = setTimeout(() => {
				setIsVisible(false);
				onClose?.();
			}, duration);
			return () => clearTimeout(timer);
		}
	}, [duration, onClose]);

	if (!isVisible) return null;

	return (
		<div
			className={cn(
				"fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg border-2 px-4 py-3 shadow-lg transition-all",
				typeStyles[type],
			)}
			role="alert"
		>
			<svg
				className="h-5 w-5 flex-shrink-0"
				fill="none"
				stroke="currentColor"
				viewBox="0 0 24 24"
				aria-hidden="true"
			>
				<path
					strokeLinecap="round"
					strokeLinejoin="round"
					strokeWidth={2}
					d={typeIcons[type]}
				/>
			</svg>
			<p className="text-sm font-medium">{message}</p>
			<button
				type="button"
				onClick={() => {
					setIsVisible(false);
					onClose?.();
				}}
				className="ml-2 rounded p-1 hover:bg-black/10"
				aria-label="Dismiss"
			>
				<svg
					className="h-4 w-4"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
					aria-hidden="true"
				>
					<path
						strokeLinecap="round"
						strokeLinejoin="round"
						strokeWidth={2}
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</button>
		</div>
	);
}

// Toast container for managing multiple toasts
interface ToastItem {
	id: string;
	message: string;
	type: ToastType;
}

interface ToastContainerProps {
	toasts: ToastItem[];
	onRemove: (id: string) => void;
}

export function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
	return (
		<div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
			{toasts.map((toast) => (
				<Toast
					key={toast.id}
					message={toast.message}
					type={toast.type}
					onClose={() => onRemove(toast.id)}
				/>
			))}
		</div>
	);
}

// Hook for managing toasts
export function useToast() {
	const [toasts, setToasts] = useState<ToastItem[]>([]);

	const addToast = (message: string, type: ToastType = "info") => {
		const id = crypto.randomUUID();
		setToasts((prev) => [...prev, { id, message, type }]);
		return id;
	};

	const removeToast = (id: string) => {
		setToasts((prev) => prev.filter((t) => t.id !== id));
	};

	return { toasts, addToast, removeToast };
}
