import Image from "next/image";
import { cn } from "@/lib/utils";

interface FeaturedEventBannerProps {
	title: string;
	subtitle: string;
	imageUrl?: string;
	ticketUrl?: string;
	className?: string;
}

export function FeaturedEventBanner({
	title,
	subtitle,
	imageUrl,
	ticketUrl = "#",
	className,
}: FeaturedEventBannerProps) {
	return (
		<div
			className={cn(
				"relative overflow-hidden rounded-sm border-2 border-text-primary bg-notebook-grid",
				className,
			)}
		>
			{/* Tape corner decorations */}
			<div className="absolute -right-3 -top-3 h-12 w-12 rotate-45 bg-gray-300/60" />
			<div className="absolute -bottom-3 -right-3 h-12 w-12 rotate-45 bg-gray-300/60" />

			<div className="flex flex-col md:flex-row">
				{/* Content side */}
				<div className="flex flex-1 flex-col justify-center p-8 md:p-12">
					{/* Featured Event label */}
					<span className="mb-4 inline-block w-fit rounded bg-category-meetup px-3 py-1 text-xs font-bold uppercase tracking-wider text-white">
						Featured Event
					</span>

					{/* Title */}
					<h2 className="mb-4 font-instrument text-4xl font-bold tracking-tight text-text-primary md:text-5xl lg:text-6xl">
						{title}
					</h2>

					{/* Subtitle on black background */}
					<div className="mb-6 inline-block w-fit bg-text-primary px-4 py-2">
						<span className="font-marker text-lg text-white">{subtitle}</span>
					</div>

					{/* Get Tickets button */}
					<a
						href={ticketUrl}
						className="inline-flex w-fit items-center gap-2 rounded border-2 border-brand-green bg-brand-green px-6 py-3 font-mono text-sm font-medium text-white transition-colors hover:bg-brand-green/90"
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
								d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
							/>
						</svg>
					</a>
				</div>

				{/* Image side */}
				{imageUrl && (
					<div className="relative h-64 md:h-auto md:w-1/2">
						<Image
							src={imageUrl}
							alt={title}
							fill
							className="object-cover"
							unoptimized
						/>
					</div>
				)}

				{/* Placeholder dark area if no image */}
				{!imageUrl && (
					<div className="relative h-64 bg-gradient-to-br from-gray-900 to-black md:h-auto md:w-1/2">
						{/* Abstract burst lines effect */}
						<div className="absolute inset-0 flex items-center justify-center opacity-30">
							<div className="h-full w-full bg-[radial-gradient(circle_at_center,_transparent_0%,_transparent_30%,_rgba(255,255,255,0.1)_31%,_transparent_32%)] bg-[length:20px_20px]" />
						</div>
					</div>
				)}
			</div>
		</div>
	);
}
