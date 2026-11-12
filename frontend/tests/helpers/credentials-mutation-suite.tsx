import { act } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { ApiError } from "@/api/errors";
import {
	expectStatusRefetchAwaited,
	renderHookWithQuery,
	requestsTo,
	statusBody,
	stubFetch,
} from "./auth-api";

interface Credentials {
	username: string;
	password: string;
}

interface Suite {
	name: string;
	path: string;
	useHook: () => {
		mutateAsync: (credentials: Credentials) => Promise<unknown>;
	};
	failure: { status: number; code: string };
}

const credentials = { username: "admin", password: "p&ss word=1+%" };
const noContent = () => new Response(null, { status: 204 });
const statusRoute = () => Response.json(statusBody);

function errorBody(code: string) {
	return { code, message: "Server text.", request_id: "abc123" };
}

export function describeCredentialsMutation({
	name,
	path,
	useHook,
	failure,
}: Suite) {
	const post = `POST ${path}`;

	function renderMutation() {
		const { result } = renderHookWithQuery(useHook);
		return {
			mutateAsync: (credentials: Credentials) =>
				result.current.value.mutateAsync(credentials),
			queryClient: result.current.queryClient,
		};
	}

	describe(name, () => {
		test("posts only the username and password as a form body and resolves on a 204", async () => {
			const fetchMock = stubFetch({
				[post]: noContent,
				"GET /api/v1/auth/status": statusRoute,
			});
			const { mutateAsync } = renderMutation();

			await act(() => mutateAsync(credentials));

			const [request] = requestsTo(fetchMock, post);
			expect(request?.credentials).toBe("same-origin");
			expect(request?.headers.get("content-type")).toBe(
				"application/x-www-form-urlencoded",
			);
			expect(
				Object.fromEntries(new URLSearchParams(await request?.text())),
			).toEqual(credentials);
			expect(new URL(request?.url ?? "").search).toBe("");
		});

		test("does not resolve until the cached status has been refetched", async () => {
			const { mutateAsync, queryClient } = renderMutation();

			await expectStatusRefetchAwaited({
				queryClient,
				postKey: post,
				mutate: () => mutateAsync(credentials),
			});
		});

		test(`rejects a ${failure.status} with an ApiError carrying ${failure.code} and leaves the status alone`, async () => {
			const body = errorBody(failure.code);
			const fetchMock = stubFetch({
				[post]: () => Response.json(body, { status: failure.status }),
			});
			const { mutateAsync } = renderMutation();

			const error = await act(() =>
				mutateAsync(credentials).catch((cause: unknown) => cause),
			);

			expect(error).toBeInstanceOf(ApiError);
			expect(error).toMatchObject({ status: failure.status, body });
			expect(requestsTo(fetchMock, "GET /api/v1/auth/status")).toHaveLength(0);
		});

		test("rejects a 400 with validation_failed", async () => {
			const body = errorBody("validation_failed");
			stubFetch({ [post]: () => Response.json(body, { status: 400 }) });
			const { mutateAsync } = renderMutation();

			const error = await act(() =>
				mutateAsync(credentials).catch((cause: unknown) => cause),
			);

			expect(error).toBeInstanceOf(ApiError);
			expect(error).toMatchObject({ status: 400, body });
		});

		test("rejects an unreadable error body with an undefined error body", async () => {
			stubFetch({
				[post]: () => new Response("<html>bad gateway</html>", { status: 502 }),
			});
			const { mutateAsync } = renderMutation();

			const error = await act(() =>
				mutateAsync(credentials).catch((cause: unknown) => cause),
			);

			expect(error).toMatchObject({ status: 502, body: undefined });
		});

		test("rejects a rejected fetch with the network error, not an ApiError", async () => {
			const networkError = new TypeError("Failed to fetch");
			vi.stubGlobal("fetch", vi.fn().mockRejectedValue(networkError));
			const { mutateAsync } = renderMutation();

			const error = await act(() =>
				mutateAsync(credentials).catch((cause: unknown) => cause),
			);

			expect(error).toBe(networkError);
		});
	});
}
