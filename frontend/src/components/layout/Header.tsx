import { cn } from "@/lib/utils";

interface HeaderProps {
	className?: string;
}

export function Header({ className }: HeaderProps) {
	return (
		<header
			className={cn(
				"flex w-full items-center justify-between px-6 py-4 md:px-12",
				className,
			)}
		>
			{/* Logo - Green badge with Tilt Warp font */}
			<div className="flex items-center">
				<div className="rounded-lg bg-brand-green px-5 py-3 shadow-md">
					<span className="logo-text text-xl font-medium text-white">
						Calendar Club
					</span>
				</div>
			</div>

			{/* Navigation - LOGIN | SUBSCRIBE with hamburger */}
			<nav className="flex items-center gap-4">
				<div className="flex items-center gap-4 rounded-md border border-border-light bg-white px-4 py-2">
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
						className="ml-2 flex h-6 w-6 flex-col items-center justify-center gap-1"
						aria-label="Open menu"
					>
						<span className="h-0.5 w-5 bg-text-primary" />
						<span className="h-0.5 w-5 bg-text-primary" />
						<span className="h-0.5 w-5 bg-text-primary" />
					</button>
				</div>
			</nav>
		</header>
	);
}
