import { cn } from "@/lib/utils";

interface HeroProps {
	className?: string;
}

export function Hero({ className }: HeroProps) {
	return (
		<div className={cn("flex flex-col gap-6", className)}>
			{/* Headline with red recording dot */}
			<div className="flex items-start gap-3">
				{/* Red recording dot indicator */}
				<div className="mt-4 h-3 w-3 flex-shrink-0 rounded-full bg-accent-red" />

				{/* Headline text */}
				<h1 className="text-5xl leading-tight md:text-6xl">
					<span className="hero-accent block">Tune into</span>
					<span className="hero-emphasis block">the signal.</span>
				</h1>
			</div>
		</div>
	);
}
