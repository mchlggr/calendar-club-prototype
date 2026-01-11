import type { NextConfig } from "next";

const nextConfig: NextConfig = {
	// API proxying is handled by the catch-all route handler at
	// src/app/api/[...path]/route.ts for better streaming support.
};

export default nextConfig;
