/**
 * Catch-all API proxy route handler.
 *
 * Proxies all /api/* requests to the FastAPI backend.
 * This is more reliable than Next.js rewrites for external URLs.
 */

import type { NextRequest } from "next/server";

function getApiTarget(): string {
	// Explicit override (dev or prod)
	const configured = process.env.API_PROXY_TARGET;
	if (configured && configured.trim().length > 0) {
		return configured.trim().replace(/\/$/, "");
	}

	// Safe dev default: proxy to local FastAPI on :8000
	if (process.env.NODE_ENV === "development") {
		return "http://127.0.0.1:8000";
	}

	// In production, require explicit configuration
	throw new Error("API_PROXY_TARGET not configured for production");
}

async function proxyRequest(
	request: NextRequest,
	path: string[],
): Promise<Response> {
	const target = getApiTarget();
	const targetPath = `/api/${path.join("/")}`;
	const targetUrl = new URL(targetPath, target);

	// Preserve query string
	const searchParams = request.nextUrl.searchParams.toString();
	if (searchParams) {
		targetUrl.search = searchParams;
	}

	// Forward headers (except host)
	const headers = new Headers();
	request.headers.forEach((value, key) => {
		if (key.toLowerCase() !== "host") {
			headers.set(key, value);
		}
	});

	// Make the proxied request
	const response = await fetch(targetUrl.toString(), {
		method: request.method,
		headers,
		body: request.body,
		// @ts-expect-error - duplex is required for streaming request bodies
		duplex: "half",
	});

	// For streaming responses, pass through directly
	if (response.headers.get("content-type")?.includes("text/event-stream")) {
		return new Response(response.body, {
			status: response.status,
			statusText: response.statusText,
			headers: {
				"Content-Type": "text/event-stream",
				"Cache-Control": "no-cache",
				Connection: "keep-alive",
				"X-Accel-Buffering": "no",
			},
		});
	}

	// For regular responses, forward as-is
	const responseHeaders = new Headers();
	response.headers.forEach((value, key) => {
		// Skip headers that Next.js handles
		if (!["transfer-encoding", "connection"].includes(key.toLowerCase())) {
			responseHeaders.set(key, value);
		}
	});

	return new Response(response.body, {
		status: response.status,
		statusText: response.statusText,
		headers: responseHeaders,
	});
}

export async function GET(
	request: NextRequest,
	{ params }: { params: Promise<{ path: string[] }> },
) {
	const { path } = await params;
	return proxyRequest(request, path);
}

export async function POST(
	request: NextRequest,
	{ params }: { params: Promise<{ path: string[] }> },
) {
	const { path } = await params;
	return proxyRequest(request, path);
}

export async function PUT(
	request: NextRequest,
	{ params }: { params: Promise<{ path: string[] }> },
) {
	const { path } = await params;
	return proxyRequest(request, path);
}

export async function DELETE(
	request: NextRequest,
	{ params }: { params: Promise<{ path: string[] }> },
) {
	const { path } = await params;
	return proxyRequest(request, path);
}

export async function PATCH(
	request: NextRequest,
	{ params }: { params: Promise<{ path: string[] }> },
) {
	const { path } = await params;
	return proxyRequest(request, path);
}
