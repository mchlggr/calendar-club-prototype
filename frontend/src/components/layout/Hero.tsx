import { cn } from "@/lib/utils";

interface HeroProps {
	className?: string;
}

export function Hero({ className }: HeroProps) {
	return (
		<div className={cn("flex flex-col gap-6", className)}>
			{/* Headline with red recording dot */}
			<div className="flex items-start gap-3">
				{/* Red recording dot */}
				<div className="mt-4 h-3.5 w-3.5 flex-shrink-0 rounded-full bg-recording-red" />

				{/* Headline text */}
				<h1 className="leading-tight">
					<span className="font-marker text-4xl italic text-brand-green md:text-5xl lg:text-6xl">
						Tune into
					</span>
					<br />
					<span className="font-instrument text-5xl text-text-primary md:text-6xl lg:text-7xl">
						the signal.
					</span>
				</h1>
			</div>
		</div>
	);
}
