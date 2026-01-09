import { cn } from "@/lib/utils";

interface StartsHereStickerProps {
	className?: string;
}

export function StartsHereSticker({ className }: StartsHereStickerProps) {
	return (
		<div
			className={cn(
				"absolute -left-2 -top-4 z-10 -rotate-6 rounded bg-paper-yellow px-3 py-1.5 shadow-md",
				className,
			)}
		>
			<span className="font-marker text-sm text-text-primary">
				Starts Here!
			</span>
		</div>
	);
}
