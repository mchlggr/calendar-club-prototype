import { Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { PromoBanner } from "./PromoBanner";

interface HeaderProps {
	className?: string;
}

export function Header({ className }: HeaderProps) {
	return (
		<header className={cn("w-full", className)}>
			<PromoBanner />

			<div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-6 py-6 md:px-12">
				{/* Logo - sticker */}
				<a
					href="/"
					className="sticker-pill tape-accent inline-flex items-center px-6 py-3 font-logo text-3xl leading-none tracking-tight transition-transform duration-200 hover:scale-105"
					style={{ "--cc-rotate": "-2deg" } as React.CSSProperties}
				>
					Calendar Club
				</a>

				{/* Actions - torn paper */}
				<nav className="flex items-center gap-3">
					<div className="paper-card relative hidden items-center gap-4 bg-bg-white p-3 tape-accent sm:flex">
						<div className="tape absolute -top-3 left-1/2 h-6 w-12 -translate-x-1/2 rotate-[-1deg]" />

						<a
							href="/login"
							className="cc-label text-text-primary transition-colors hover:text-brand-green"
						>
							Login
						</a>
						<span className="text-border-light">|</span>
						<a
							href="/subscribe"
							className="cc-label text-text-primary transition-colors hover:text-brand-green"
						>
							Subscribe
						</a>
						<button
							type="button"
							className="btn-brutal cc-btn-icon"
							aria-label="Open menu"
						>
							<Menu className="h-4 w-4" aria-hidden="true" />
						</button>
					</div>

					{/* Mobile menu button */}
					<button
						type="button"
						className="btn-brutal cc-btn-icon sm:hidden"
						aria-label="Open menu"
					>
						<Menu className="h-5 w-5" aria-hidden="true" />
					</button>
				</nav>
			</div>
		</header>
	);
}
