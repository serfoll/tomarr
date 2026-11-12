import { act } from "@testing-library/react";
import { expect, test } from "vitest";
import { ApiError } from "@/api/errors";
import { authStatusKey, authStatusQueryOptions } from "@/api/use-auth-status";
import { useSignOut } from "@/api/use-sign-out";
import {
	expectStatusRefetchAwaited,
	renderHookWithQuery,
	requestsTo,
	statusBody,
	stubFetch,
} from "../helpers/auth-api";

function renderUseSignOut() {
	const { result } = renderHookWithQuery(useSignOut);
	return {
		mutateAsync: () => result.current.value.mutateAsync(),
		queryClient: result.current.queryClient,
	};
}

test("posts to logout with no body and refetches the status after a 204", async () => {
	const signedOut = { ...statusBody, authenticated: false };
	stubFetch({ "GET /api/v1/auth/status": () => Response.json(statusBody) });
	const { mutateAsync, queryClient } = renderUseSignOut();
	await queryClient.fetchQuery(authStatusQueryOptions);
	const fetchMock = stubFetch({
		"POST /api/v1/auth/logout": () => new Response(null, { status: 204 }),
		"GET /api/v1/auth/status": () => Response.json(signedOut),
	});

	await act(() => mutateAsync());

	const [request] = requestsTo(fetchMock, "POST /api/v1/auth/logout");
	expect(request?.credentials).toBe("same-origin");
	expect(request?.body).toBeNull();
	expect(request?.headers.has("content-type")).toBe(false);
	expect(requestsTo(fetchMock, "GET /api/v1/auth/status")).toHaveLength(1);
	expect(queryClient.getQueryData(authStatusKey)).toEqual(signedOut);
});

test("does not resolve until the cached status has been refetched", async () => {
	const { mutateAsync, queryClient } = renderUseSignOut();

	await expectStatusRefetchAwaited({
		queryClient,
		postKey: "POST /api/v1/auth/logout",
		mutate: () => mutateAsync(),
	});
});

test("rejects a 500 with an ApiError and leaves the status alone", async () => {
	const body = {
		code: "internal_error",
		message: "Server text.",
		request_id: "abc123",
	};
	const fetchMock = stubFetch({
		"POST /api/v1/auth/logout": () => Response.json(body, { status: 500 }),
	});
	const { mutateAsync } = renderUseSignOut();

	const error = await act(() => mutateAsync().catch((cause: unknown) => cause));

	expect(error).toBeInstanceOf(ApiError);
	expect(error).toMatchObject({ status: 500, body });
	expect(requestsTo(fetchMock, "GET /api/v1/auth/status")).toHaveLength(0);
});

test("rejects a rejected fetch with the network error", async () => {
	const networkError = new TypeError("Failed to fetch");
	stubFetch({
		"POST /api/v1/auth/logout": () => {
			throw networkError;
		},
	});
	const { mutateAsync } = renderUseSignOut();

	const error = await act(() => mutateAsync().catch((cause: unknown) => cause));

	expect(error).toBe(networkError);
});
