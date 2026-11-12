import { useQuery } from "@tanstack/react-query";
import { client } from "@/api/client";
import { apiErrorFrom, UnreadableResponseError } from "@/api/errors";
import { trackResponse } from "@/api/track-response";

const unreadableMessage = "The response is not a system status";

async function getSystemStatus() {
	const tracked = trackResponse(unreadableMessage);
	const { data, error, response } = await client
		.GET("/api/v1/system/status", { fetch: tracked.fetch })
		.catch(tracked.rethrow);
	if (!response.ok) {
		throw apiErrorFrom(response.status, error);
	}
	// A 204 or an empty body has no data, and the schema type does not know a version can be missing or blank.
	const version: unknown = data?.version;
	if (typeof version !== "string" || version.trim() === "") {
		throw new UnreadableResponseError(unreadableMessage);
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
