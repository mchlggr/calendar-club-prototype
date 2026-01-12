import type { Metadata } from "next";
import {
	Instrument_Serif,
	Inter,
	JetBrains_Mono,
	Nunito,
	Permanent_Marker,
	Tilt_Warp,
} from "next/font/google";
import Script from "next/script";
import { Suspense } from "react";
import "@/styles/globals.css";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { PostHogProvider } from "@/components/PostHogProvider";
import { TelemetryProvider } from "@/components/TelemetryProvider";

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

const nunito = Nunito({
	variable: "--font-nunito",
	subsets: ["latin"],
	weight: ["700", "800", "900"],
});

export const metadata: Metadata = {
	title: "Calendar Club",
	description:
		"Discover in-person events and download a calendar file for your week.",
};

export default function RootLayout({
	children,
	calendar,
}: Readonly<{
	children: React.ReactNode;
	calendar: React.ReactNode;
}>) {
	return (
		<html lang="en">
			<head>
				{process.env.NODE_ENV === "development" && (
					<>
						<Script
							src="//unpkg.com/react-grab/dist/index.global.js"
							strategy="beforeInteractive"
						/>
						<Script
							src="//unpkg.com/@react-grab/claude-code/dist/client.global.js"
							strategy="lazyOnload"
						/>
					</>
				)}
			</head>
			<body
				className={`${inter.variable} ${jetbrainsMono.variable} ${permanentMarker.variable} ${instrumentSerif.variable} ${tiltWarp.variable} ${nunito.variable} min-h-screen bg-page font-sans antialiased`}
			>
				<Suspense fallback={null}>
					<PostHogProvider>
						<TelemetryProvider>
							<Header />
							<main>{children}</main>
							<Footer />
							{calendar}
						</TelemetryProvider>
					</PostHogProvider>
				</Suspense>
			</body>
		</html>
	);
}
