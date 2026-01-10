import type { Metadata } from "next";
import {
	Instrument_Serif,
	Inter,
	JetBrains_Mono,
	Permanent_Marker,
	Tilt_Warp,
} from "next/font/google";
import { Suspense } from "react";
import "@/styles/globals.css";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { PostHogProvider } from "@/components/PostHogProvider";
import { TelemetryProvider } from "@/components/TelemetryProvider";
import { QueryProvider } from "@/lib/query-provider";

const inter = Inter({
	variable: "--font-inter",
	subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
	variable: "--font-jetbrains",
	subsets: ["latin"],
});

const permanentMarker = Permanent_Marker({
	variable: "--font-marker",
	subsets: ["latin"],
	weight: "400",
});

const instrumentSerif = Instrument_Serif({
	variable: "--font-instrument",
	subsets: ["latin"],
	weight: "400",
	style: ["normal", "italic"],
});

const tiltWarp = Tilt_Warp({
	variable: "--font-tilt-warp",
	subsets: ["latin"],
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
				className={`${inter.variable} ${jetbrainsMono.variable} ${permanentMarker.variable} ${instrumentSerif.variable} ${tiltWarp.variable} min-h-screen bg-bg-cream font-sans antialiased`}
			>
				<Suspense fallback={null}>
					<PostHogProvider>
						<TelemetryProvider>
							<QueryProvider>
								<Header />
								<main>{children}</main>
								<Footer />
							</QueryProvider>
						</TelemetryProvider>
					</PostHogProvider>
				</Suspense>
			</body>
		</html>
	);
}
