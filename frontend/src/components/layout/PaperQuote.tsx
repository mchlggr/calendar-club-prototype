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
						&ldquo;A curated directory of the best technical meetups. No noise,
						just deep cuts.&rdquo;
					</>
				)}
			</p>
		</div>
	);
}
