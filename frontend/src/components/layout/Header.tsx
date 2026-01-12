import Link from "next/link";
import { cn } from "@/lib/utils";
import { PaperQuote } from "./PaperQuote";

interface HeaderProps {
	className?: string;
}

export function Header({ className }: HeaderProps) {
	return (
		<header className={cn("w-full", className)}>
			<div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-6 px-6 py-6 md:px-12">
				{/* Logo - sticker */}
				<Link
					href="/"
					className="sticker-pill tape-accent inline-flex items-center px-6 py-3 font-logo text-3xl leading-none tracking-tight transition-transform duration-200 hover:scale-105"
					style={{ "--cc-rotate": "-2deg" } as React.CSSProperties}
				>
					Calendar Club
                </Link>
                <PaperQuote	/>
			</div>
		</header>
	);
}
