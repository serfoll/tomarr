import {
	QueryClient,
	QueryClientProvider,
	useQueryClient,
} from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { expect, vi } from "vitest";
import type { Credentials } from "@/api/form-body";
import { authStatusKey, authStatusQueryOptions } from "@/api/use-auth-status";

export const statusBody = {
	setup_required: false,
	authenticated: true,
	password_min_length: 12,
};

function Wrapper({ children }: { children: ReactNode }) {
	const [queryClient] = useState(
		() => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
	);
	return (
		<QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
	);
}

// The query client is created by the wrapper, so it comes back next to the hook's value.
export function renderHookWithQuery<T>(callback: () => T) {
	return renderHook(
		() => ({ value: callback(), queryClient: useQueryClient() }),
		{ wrapper: Wrapper },
	);
}

type Route = (request: Request) => Response | Promise<Response>;

// Routes are keyed "METHOD /path". An unrouted request fails the test instead of answering.
export function stubFetch(routes: Record<string, Route>) {
	const fetchMock = vi.fn(async (request: Request) => {
		const key = `${request.method} ${new URL(request.url).pathname}`;
		const route = routes[key];
		if (route === undefined) {
			throw new Error(`Unexpected request: ${key}`);
		}
		return route(request);
	});
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

export function errorBody(code: string) {
	return { code, message: "Server text.", request_id: "abc123" };
}

export const noContent = () => new Response(null, { status: 204 });

// Holds the request open until the test releases it, then lets the given route answer.
export function heldRoute(route: Route) {
	let release = () => {};
	const released = new Promise<void>((resolve) => {
		release = resolve;
	});
	return {
		route: async (request: Request) => {
			await released;
			return route(request);
		},
		release: () => release(),
	};
}

// A clone, so a test can still read the body of the request it finds in the mock's calls.
async function sentCredentials(request: Request): Promise<Credentials> {
	const form = new URLSearchParams(await request.clone().text());
	return {
		username: form.get("username") ?? "",
		password: form.get("password") ?? "",
	};
}

type FakeAuthPath =
	| "GET /api/v1/auth/status"
	| "POST /api/v1/auth/setup"
	| "POST /api/v1/auth/login"
	| "POST /api/v1/auth/logout"
	| "GET /api/v1/system/status";

interface FakeAuthOptions {
	credentials?: Credentials;
	signedIn?: boolean;
	passwordMinLength?: number;
}

// Answers like the backend: sign-up stores the credentials and signs in, and the session decides the rest.
export function fakeAuthBackend({
	credentials,
	signedIn = false,
	passwordMinLength = 8,
}: FakeAuthOptions = {}) {
	const state = { credentials, signedIn };
	const routes: Record<FakeAuthPath, Route> = {
		"GET /api/v1/auth/status": () =>
			Response.json({
				setup_required: state.credentials === undefined,
				authenticated: state.signedIn,
				password_min_length: passwordMinLength,
			}),
		"POST /api/v1/auth/setup": async (request) => {
			if (state.credentials !== undefined) {
				return Response.json(errorBody("setup_already_done"), { status: 409 });
			}
			state.credentials = await sentCredentials(request);
			state.signedIn = true;
			return noContent();
		},
		"POST /api/v1/auth/login": async (request) => {
			const sent = await sentCredentials(request);
			if (
				sent.username !== state.credentials?.username ||
				sent.password !== state.credentials.password
			) {
				return Response.json(errorBody("invalid_credentials"), { status: 401 });
			}
			state.signedIn = true;
			return noContent();
		},
		"POST /api/v1/auth/logout": () => {
			state.signedIn = false;
			return noContent();
		},
		"GET /api/v1/system/status": () =>
			state.signedIn
				? Response.json({ version: "1.2.3" })
				: Response.json(errorBody("not_authenticated"), { status: 401 }),
	};
	return { state, routes };
}

export function requestsTo(
	fetchMock: ReturnType<typeof stubFetch>,
	key: string,
): Request[] {
	return fetchMock.mock.calls
		.map(([request]) => request)
		.filter(
			(request) => `${request.method} ${new URL(request.url).pathname}` === key,
		);
}

const statusPath = "GET /api/v1/auth/status";

// The cache is seeded through the query options, as the route guard does, so it holds a query with no observer.
export async function expectStatusRefetchAwaited({
	queryClient,
	postKey,
	mutate,
}: {
	queryClient: QueryClient;
	postKey: string;
	mutate: () => Promise<unknown>;
}) {
	const staleStatus = { ...statusBody, authenticated: false };
	stubFetch({ [statusPath]: () => Response.json(staleStatus) });
	await queryClient.fetchQuery(authStatusQueryOptions);

	let releaseStatus = () => {};
	const statusGate = new Promise<void>((resolve) => {
		releaseStatus = resolve;
	});
	const fetchMock = stubFetch({
		[postKey]: () => new Response(null, { status: 204 }),
		[statusPath]: async () => {
			await statusGate;
			return Response.json(statusBody);
		},
	});
	let settled = false;
	let mutation = Promise.resolve();
	act(() => {
		mutation = mutate().then(() => {
			settled = true;
		});
	});

	await waitFor(() =>
		expect(requestsTo(fetchMock, statusPath)).toHaveLength(1),
	);
	await new Promise((resolve) => setTimeout(resolve, 20));
	expect(settled).toBe(false);
	expect(queryClient.getQueryData(authStatusKey)).toEqual(staleStatus);

	await act(async () => {
		releaseStatus();
		await mutation;
	});
	expect(settled).toBe(true);
	expect(queryClient.getQueryData(authStatusKey)).toEqual(statusBody);
}
