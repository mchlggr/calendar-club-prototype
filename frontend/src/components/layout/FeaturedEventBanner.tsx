import { cn } from "@/lib/utils";

interface FeaturedEventBannerProps {
	title: string;
	subtitle: string;
	ticketUrl?: string;
	imageUrl?: string;
	className?: string;
}

export function FeaturedEventBanner({
	title,
	subtitle,
	ticketUrl,
	imageUrl,
	className,
}: FeaturedEventBannerProps) {
	return (
		<div
			className={cn(
				"relative overflow-hidden rounded-lg border-2 border-border-light bg-notebook-grid shadow-lg",
				className,
			)}
		>
			{/* Tape corners */}
			<div className="tape-corner tape-corner-tl" />
			<div className="tape-corner tape-corner-tr" />
			<div className="tape-corner tape-corner-bl" />
			<div className="tape-corner tape-corner-br" />

			<div className="flex">
				{/* Content side */}
				<div className="flex-1 p-8">
					{/* Featured Event badge */}
					<span className="mb-4 inline-block rounded bg-accent-orange px-3 py-1 text-xs font-semibold uppercase tracking-wider text-white">
						Featured Event
					</span>

					{/* Title */}
					<h2 className="hero-emphasis mb-4 text-4xl font-bold md:text-5xl">
						{title}
					</h2>

					{/* Subtitle with black background */}
					<div className="mb-6 inline-block bg-black px-3 py-1">
						<span className="tagline text-white">{subtitle}</span>
					</div>

					{/* Get Tickets button */}
					{ticketUrl && (
						<div>
							<a
								href={ticketUrl}
								target="_blank"
								rel="noopener noreferrer"
								className="inline-flex items-center gap-2 rounded-md border-2 border-brand-green bg-brand-green px-6 py-3 font-medium text-white transition-colors hover:bg-brand-green/90"
							>
								Get Tickets
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
										d="M17 8l4 4m0 0l-4 4m4-4H3"
									/>
								</svg>
							</a>
						</div>
					)}
				</div>

				{/* Image side */}
				{imageUrl ? (
					<div
						className="hidden w-1/2 bg-cover bg-center md:block"
						style={{ backgroundImage: `url(${imageUrl})` }}
					/>
				) : (
					<div className="hidden w-1/2 bg-black md:block">
						{/* Abstract light rays effect */}
						<div className="flex h-full items-center justify-center">
							<div className="relative h-full w-full overflow-hidden">
								<div className="absolute inset-0 bg-gradient-radial from-zinc-700/30 via-transparent to-transparent" />
							</div>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
