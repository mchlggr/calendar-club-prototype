import { cn } from "@/lib/utils";

interface PaperQuoteProps {
	className?: string;
	children?: React.ReactNode;
}

export function PaperQuote({ className, children }: PaperQuoteProps) {
	return (
		<div
			className={cn("paper-quote inline-block max-w-md rounded-sm", className)}
		>
			<p className="font-marker text-lg leading-relaxed text-text-primary md:text-xl">
				{children || (
					<>
						&ldquo;Find events and meetups, then download a calendar file for
						your week.&rdquo;
					</>
				)}
			</p>
		</div>
	);
}
