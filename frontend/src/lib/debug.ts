/**
 * Debug logging utility for event flow tracing.
 * Enable with: localStorage.setItem('DEBUG_EVENTS', 'true')
 * Disable with: localStorage.removeItem('DEBUG_EVENTS')
 */

const isDebugEnabled = (): boolean => {
	if (typeof window === "undefined") return false;
	return localStorage.getItem("DEBUG_EVENTS") === "true";
};

export const debugLog = (
	component: string,
	message: string,
	data?: Record<string, unknown>,
): void => {
	if (!isDebugEnabled()) return;

	const timestamp = new Date().toISOString().slice(11, 23); // HH:mm:ss.SSS
	const dataStr = data
		? ` | ${Object.entries(data)
				.map(([k, v]) => `${k}=${JSON.stringify(v)}`)
				.join(" ")}`
		: "";
	console.debug(`[${timestamp}] [${component}] ${message}${dataStr}`);
};

export const debugWarn = (
	component: string,
	message: string,
	data?: Record<string, unknown>,
): void => {
	if (!isDebugEnabled()) return;

	const timestamp = new Date().toISOString().slice(11, 23);
	const dataStr = data
		? ` | ${Object.entries(data)
				.map(([k, v]) => `${k}=${JSON.stringify(v)}`)
				.join(" ")}`
		: "";
	console.warn(`[${timestamp}] [${component}] ${message}${dataStr}`);
};
