import { useQuery } from "@tanstack/react-query";
import { client } from "@/api/client";
import {
	ApiError,
	type ErrorResponse,
	UnreadableResponseError,
} from "@/api/errors";

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

async function getSystemStatus() {
	// openapi-fetch parses a success body itself and a malformed one rejects with a SyntaxError.
	// Only a SyntaxError raised after the response arrived is a body problem, so a failure inside fetch passes through.
	let responded = false;
	const { data, error, response } = await client
		.GET("/api/v1/system/status", {
			fetch: async (request) => {
				const received = await globalThis.fetch(request);
				responded = true;
				return received;
			},
		})
		.catch((cause: unknown) => {
			// A network failure rejects with a TypeError and must stay that way.
			throw responded && cause instanceof SyntaxError
				? new UnreadableResponseError()
				: cause;
		});
	if (!response.ok) {
		throw new ApiError(
			response.status,
			isErrorResponse(error) ? error : undefined,
		);
	}
	// A 204 or an empty body has no data, and the schema type does not know a version can be missing or blank.
	const version: unknown = data?.version;
	if (typeof version !== "string" || version.trim() === "") {
		throw new UnreadableResponseError();
	}
	return { version };
}

export function useSystemStatus() {
	return useQuery({
		queryKey: ["system", "status"],
		queryFn: getSystemStatus,
		// Retrying cannot fix a 401 and would leave the loading text up for seconds.
		retry: false,
	});
}
