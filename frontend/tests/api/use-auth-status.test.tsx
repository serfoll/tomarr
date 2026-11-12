import { waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ApiError, UnreadableResponseError } from "@/api/errors";
import { authStatusKey, useAuthStatus } from "@/api/use-auth-status";
import { renderHookWithQuery, statusBody } from "../helpers/auth-api";

function renderUseAuthStatus() {
	const { result } = renderHookWithQuery(useAuthStatus);
	return {
		result: {
			get current() {
				return result.current.value;
			},
		},
		queryClient: result.current.queryClient,
	};
}

test("requests the auth status same-origin and returns the four fields", async () => {
	const fetchMock = vi.fn().mockResolvedValue(Response.json(statusBody));
	vi.stubGlobal("fetch", fetchMock);

	const { result, queryClient } = renderUseAuthStatus();

	await waitFor(() => expect(result.current.isSuccess).toBe(true));
	expect(result.current.data).toEqual(statusBody);
	expect(queryClient.getQueryData(authStatusKey)).toEqual(statusBody);
	expect(fetchMock).toHaveBeenCalledTimes(1);
	const request: Request = fetchMock.mock.calls[0]?.[0];
	expect(request.method).toBe("GET");
	expect(new URL(request.url).pathname).toBe("/api/v1/auth/status");
	expect(request.credentials).toBe("same-origin");
	expect([...request.headers]).toEqual([]);
});

test("rejects a non-ok status with an ApiError carrying the typed error body", async () => {
	const body = {
		code: "internal_error",
		message: "Something went wrong.",
		request_id: "abc123",
	};
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(Response.json(body, { status: 500 })),
	);

	const { result } = renderUseAuthStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBeInstanceOf(ApiError);
	expect(result.current.error).toMatchObject({ status: 500, body });
});

test("rejects a non-ok status with an unknown body with an undefined error body", async () => {
	vi.stubGlobal(
		"fetch",
		vi
			.fn()
			.mockResolvedValue(
				new Response("<html>bad gateway</html>", { status: 502 }),
			),
	);

	const { result } = renderUseAuthStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toMatchObject({ status: 502, body: undefined });
});

test("rejects a rejected fetch with the network error, not an ApiError", async () => {
	const networkError = new TypeError("Failed to fetch");
	vi.stubGlobal("fetch", vi.fn().mockRejectedValue(networkError));

	const { result } = renderUseAuthStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBe(networkError);
});

test.each([
	["null", () => Response.json(null)],
	["an empty object", () => Response.json({})],
	[
		"a missing setup_required",
		() => Response.json({ ...statusBody, setup_required: undefined }),
	],
	[
		"a string setup_required",
		() => Response.json({ ...statusBody, setup_required: "false" }),
	],
	[
		"a missing authenticated",
		() => Response.json({ ...statusBody, authenticated: undefined }),
	],
	[
		"a null authenticated",
		() => Response.json({ ...statusBody, authenticated: null }),
	],
	[
		"a missing password_min_length",
		() => Response.json({ ...statusBody, password_min_length: undefined }),
	],
	[
		"a string password_min_length",
		() => Response.json({ ...statusBody, password_min_length: "12" }),
	],
	[
		"a missing password_max_length",
		() => Response.json({ ...statusBody, password_max_length: undefined }),
	],
	[
		"a string password_max_length",
		() => Response.json({ ...statusBody, password_max_length: "256" }),
	],
	["invalid JSON", () => new Response("<html>proxy page</html>")],
	["a 204", () => new Response(null, { status: 204 })],
])("rejects a success response with %s as unreadable", async (_, response) => {
	vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));

	const { result } = renderUseAuthStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBeInstanceOf(UnreadableResponseError);
});

test("rejects a SyntaxError thrown by fetch itself as that error, not as unreadable", async () => {
	const failure = new SyntaxError("not from a response body");
	vi.stubGlobal("fetch", vi.fn().mockRejectedValue(failure));

	const { result } = renderUseAuthStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBe(failure);
});
