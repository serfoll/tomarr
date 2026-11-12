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

export async function getSystemStatus(): Promise<SystemStatus> {
	const response = await fetch("/api/v1/system/status", {
		credentials: "same-origin",
	});
	if (!response.ok) {
		throw new ApiError(response.status);
	}
	return (await response.json()) as SystemStatus;
}
