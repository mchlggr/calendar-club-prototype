"use client";

import { useEffect } from "react";
import { initTelemetry, trackBoomerangReturn } from "@/lib/telemetry";

export function TelemetryProvider({ children }: { children: React.ReactNode }) {
	useEffect(() => {
		// Initialize HyperDX telemetry
		initTelemetry();

		// Check for boomerang return (user came back after clicking out)
		trackBoomerangReturn();
	}, []);

	return <>{children}</>;
}
