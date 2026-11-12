import type { components } from "@/api/schema.gen";

export type ErrorResponse = components["schemas"]["ErrorResponse"];

export class ApiError extends Error {
	readonly status: number;
	readonly body: ErrorResponse | undefined;

	constructor(status: number, body?: ErrorResponse) {
		super(`Request failed with status ${status}`);
		this.name = "ApiError";
		this.status = status;
		this.body = body;
	}
}

export class UnreadableResponseError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "UnreadableResponseError";
	}
}

// The client types an error body as ErrorResponse, but a proxy page or an empty body reaches it as a string or undefined.
function isErrorResponse(body: unknown): body is ErrorResponse {
	return (
		typeof body === "object" &&
		body !== null &&
		"code" in body &&
		typeof body.code === "string" &&
		"message" in body &&
		typeof body.message === "string" &&
		"request_id" in body &&
		typeof body.request_id === "string"
	);
}

export function apiErrorFrom(status: number, body: unknown): ApiError {
	return new ApiError(status, isErrorResponse(body) ? body : undefined);
}
