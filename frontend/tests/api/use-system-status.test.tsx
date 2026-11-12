import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { expect, test, vi } from "vitest";
import { ApiError, UnreadableResponseError } from "@/api/errors";
import { useSystemStatus } from "@/api/use-system-status";

function Wrapper({ children }: { children: ReactNode }) {
	const [client] = useState(() => new QueryClient());
	return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderUseSystemStatus() {
	return renderHook(() => useSystemStatus(), { wrapper: Wrapper });
}

test("requests the status same-origin with no extra headers", async () => {
	const fetchMock = vi
		.fn()
		.mockResolvedValue(Response.json({ version: "1.2.3" }));
	vi.stubGlobal("fetch", fetchMock);

	const { result } = renderUseSystemStatus();

	await waitFor(() => expect(result.current.isSuccess).toBe(true));
	expect(result.current.data).toEqual({ version: "1.2.3" });
	expect(fetchMock).toHaveBeenCalledTimes(1);
	const request: Request = fetchMock.mock.calls[0]?.[0];
	expect(request.method).toBe("GET");
	expect(new URL(request.url).pathname).toBe("/api/v1/system/status");
	expect(request.credentials).toBe("same-origin");
	expect([...request.headers]).toEqual([]);
});

test("rejects a 401 with an ApiError carrying the typed error body", async () => {
	const body = {
		code: "not_authenticated",
		message: "Sign in first.",
		request_id: "abc123",
	};
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(Response.json(body, { status: 401 })),
	);

	const { result } = renderUseSystemStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBeInstanceOf(ApiError);
	expect(result.current.error).toMatchObject({ status: 401, body });
});

test.each([
	["no body", () => new Response(null, { status: 401 })],
	["an html body", () => new Response("<html>nope</html>", { status: 401 })],
	[
		"a json body of the wrong shape",
		() => Response.json({ detail: "no" }, { status: 401 }),
	],
])(
	"rejects a 401 with %s with an undefined error body",
	async (_, response) => {
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));

		const { result } = renderUseSystemStatus();

		await waitFor(() => expect(result.current.isError).toBe(true));
		expect(result.current.error).toBeInstanceOf(ApiError);
		expect(result.current.error).toMatchObject({
			status: 401,
			body: undefined,
		});
	},
);

test("rejects a rejected fetch with the network error, not an ApiError", async () => {
	const networkError = new TypeError("Failed to fetch");
	vi.stubGlobal("fetch", vi.fn().mockRejectedValue(networkError));

	const { result } = renderUseSystemStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBe(networkError);
	expect(result.current.error).not.toBeInstanceOf(ApiError);
});

test.each([
	["null", () => Response.json(null)],
	["an empty object", () => Response.json({})],
	["a number version", () => Response.json({ version: 1 })],
	["an object version", () => Response.json({ version: { major: 1 } })],
	["an empty version", () => Response.json({ version: "" })],
	["a whitespace-only version", () => Response.json({ version: "   " })],
	["invalid JSON", () => new Response("<html>proxy page</html>")],
	["a 204", () => new Response(null, { status: 204 })],
])("rejects a success response with %s as unreadable", async (_, response) => {
	vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));

	const { result } = renderUseSystemStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBeInstanceOf(UnreadableResponseError);
});

test("rejects a SyntaxError thrown by fetch itself as that error, not as unreadable", async () => {
	const failure = new SyntaxError("not from a response body");
	vi.stubGlobal("fetch", vi.fn().mockRejectedValue(failure));

	const { result } = renderUseSystemStatus();

	await waitFor(() => expect(result.current.isError).toBe(true));
	expect(result.current.error).toBe(failure);
	expect(result.current.error).not.toBeInstanceOf(UnreadableResponseError);
});
