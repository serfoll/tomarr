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
	constructor() {
		super("The response is not a system status");
		this.name = "UnreadableResponseError";
	}
}
