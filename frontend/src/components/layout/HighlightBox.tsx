import { cn } from "@/lib/utils";

interface HighlightBoxProps {
	children: React.ReactNode;
	className?: string;
}

export function HighlightBox({ children, className }: HighlightBoxProps) {
	return (
		<div className={cn("highlight-box inline-block max-w-md", className)}>
			<p className="tagline text-text-primary">&quot;{children}&quot;</p>
		</div>
	);
}
