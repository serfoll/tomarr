import type { ProxyOptions } from "vite";

const BACKEND_URL = "http://127.0.0.1:8000";

export function apiProxy(
	apiKey: string | undefined,
): Record<string, ProxyOptions> {
	if (!apiKey) {
		return { "/api": { target: BACKEND_URL } };
	}
	return { "/api": { target: BACKEND_URL, headers: { "X-Api-Key": apiKey } } };
}
