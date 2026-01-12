import { cn } from "@/lib/utils";

interface PaperQuoteProps {
	className?: string;
	children?: React.ReactNode;
}

export function PaperQuote({ className, children }: PaperQuoteProps) {
	return (
		<div
			className={cn(
				"highlight-box tape-accent inline-block max-w-md",
				className,
			)}
			style={{ "--cc-rotate": "1.5deg" } as React.CSSProperties}
		>
			<p className="highlight-quote">
				{children || (
					<>
						&ldquo;Deep research search for events,<br/>
						synced to your calendar.&rdquo;
					</>
				)}
			</p>
		</div>
	);
}
