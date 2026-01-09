import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Header } from "@/components/layout";
import "@/styles/globals.css";
import { QueryProvider } from "@/lib/query-provider";

const geistSans = Geist({
	variable: "--font-geist-sans",
	subsets: ["latin"],
});

const geistMono = Geist_Mono({
	variable: "--font-geist-mono",
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
				className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-bg-cream font-sans antialiased`}
			>
				<QueryProvider>
					<Header />
					<main>{children}</main>
				</QueryProvider>
			</body>
		</html>
	);
}
