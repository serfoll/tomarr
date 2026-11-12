// The one hand-written request. #13 replaces it with the generated API client.

export interface SystemStatus {
	version: string;
}

export class ApiError extends Error {
	readonly status: number;

	constructor(status: number) {
		super(`Request failed with status ${status}`);
		this.name = "ApiError";
		this.status = status;
	}
}

export class UnreadableResponseError extends Error {
	constructor() {
		super("The response is not a system status");
		this.name = "UnreadableResponseError";
	}
}

function isSystemStatus(body: unknown): body is SystemStatus {
	return (
		typeof body === "object" &&
		body !== null &&
		"version" in body &&
		typeof body.version === "string" &&
		body.version !== ""
	);
}

export async function getSystemStatus(): Promise<SystemStatus> {
	const response = await fetch("/api/v1/system/status", {
		credentials: "same-origin",
	});
	if (!response.ok) {
		throw new ApiError(response.status);
	}
	// A proxy page or an empty body is not a network failure, so it must not reject as one.
	const body: unknown = await response.json().catch(() => null);
	if (!isSystemStatus(body)) {
		throw new UnreadableResponseError();
	}
	return body;
}
