import {
	type QueryClient,
	queryOptions,
	useQuery,
} from "@tanstack/react-query";
import { client } from "@/api/client";
import { apiErrorFrom, UnreadableResponseError } from "@/api/errors";
import type { components } from "@/api/schema.gen";
import { trackResponse } from "@/api/track-response";

export type AuthStatus = components["schemas"]["AuthStatus"];

export const authStatusKey = ["auth", "status"] as const;

const unreadableMessage = "The response is not an auth status";

// The schema type does not know a proxy page or an older backend can answer with a body of another shape.
function isAuthStatus(body: unknown): body is AuthStatus {
	return (
		typeof body === "object" &&
		body !== null &&
		"setup_required" in body &&
		typeof body.setup_required === "boolean" &&
		"authenticated" in body &&
		typeof body.authenticated === "boolean" &&
		"password_min_length" in body &&
		typeof body.password_min_length === "number"
	);
}

async function getAuthStatus(): Promise<AuthStatus> {
	const tracked = trackResponse(unreadableMessage);
	const { data, error, response } = await client
		.GET("/api/v1/auth/status", { fetch: tracked.fetch })
		.catch(tracked.rethrow);
	if (!response.ok) {
		throw apiErrorFrom(response.status, error);
	}
	if (!isAuthStatus(data)) {
		throw new UnreadableResponseError(unreadableMessage);
	}
	return {
		setup_required: data.setup_required,
		authenticated: data.authenticated,
		password_min_length: data.password_min_length,
	};
}

export const authStatusQueryOptions = queryOptions({
	queryKey: authStatusKey,
	queryFn: getAuthStatus,
	// Retrying cannot fix a 401 and would leave the loading text up for seconds.
	retry: false,
});

export function useAuthStatus() {
	return useQuery(authStatusQueryOptions);
}

// "all" also refetches the status when nothing is watching it, as with the route guard, which reads it through ensureQueryData.
export function refetchAuthStatus(queryClient: QueryClient) {
	return queryClient.invalidateQueries({
		queryKey: authStatusKey,
		refetchType: "all",
	});
}
