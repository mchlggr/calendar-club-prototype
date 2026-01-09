import type { Metadata } from "next";
import { Geist, Geist_Mono, Playfair_Display } from "next/font/google";
import "@/styles/globals.css";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { TelemetryProvider } from "@/components/TelemetryProvider";
import { QueryProvider } from "@/lib/query-provider";

const geistSans = Geist({
	variable: "--font-geist-sans",
	subsets: ["latin"],
});

const geistMono = Geist_Mono({
	variable: "--font-geist-mono",
	subsets: ["latin"],
});

const playfairSerif = Playfair_Display({
	variable: "--font-serif",
	subsets: ["latin"],
	style: ["normal", "italic"],
});

export const metadata: Metadata = {
	title: "Calendar Club | Discover Local Tech Events",
	description:
		"A curated directory of the best technical meetups. No noise, just deep cuts.",
};

export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html lang="en">
			<body
				className={`${geistSans.variable} ${geistMono.variable} ${playfairSerif.variable} min-h-screen bg-bg-cream font-sans antialiased`}
			>
				<TelemetryProvider>
					<QueryProvider>
						<Header />
						<main>{children}</main>
						<Footer />
					</QueryProvider>
				</TelemetryProvider>
			</body>
		</html>
	);
}
