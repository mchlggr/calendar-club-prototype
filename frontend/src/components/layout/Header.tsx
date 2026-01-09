import { cn } from "@/lib/utils";

interface HeaderProps {
	className?: string;
}

export function Header({ className }: HeaderProps) {
	return (
		<header
			className={cn(
				"flex w-full items-center justify-between px-6 py-6 md:px-12",
				className,
			)}
		>
			{/* Logo - Green badge with Tilt Warp font */}
			<div className="flex items-center">
				<div className="rounded-lg bg-brand-green px-5 py-3 shadow-md">
					<span className="font-tilt-warp text-xl text-white tracking-wide">
						Calendar Club
					</span>
				</div>
			</div>

			{/* Navigation */}
			<nav className="flex items-center gap-4">
				<div className="flex items-center gap-4 rounded-full border border-border-light bg-white px-5 py-2.5 shadow-sm">
					<a
						href="/login"
						className="text-sm font-medium uppercase tracking-wider text-text-primary transition-colors hover:text-brand-green"
					>
						Login
					</a>
					<span className="text-border-light">|</span>
					<a
						href="/subscribe"
						className="text-sm font-medium uppercase tracking-wider text-text-primary transition-colors hover:text-brand-green"
					>
						Subscribe
					</a>
					{/* Hamburger menu icon */}
					<button
						type="button"
						className="ml-2 flex h-6 w-6 items-center justify-center text-text-primary transition-colors hover:text-brand-green"
						aria-label="Open menu"
					>
						<svg
							className="h-5 w-5"
							fill="none"
							stroke="currentColor"
							viewBox="0 0 24 24"
							aria-hidden="true"
						>
							<path
								strokeLinecap="round"
								strokeLinejoin="round"
								strokeWidth={2}
								d="M4 6h16M4 12h16M4 18h16"
							/>
						</svg>
					</button>
				</div>
			</nav>
		</header>
	);
}
