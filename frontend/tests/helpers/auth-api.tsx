import {
	QueryClient,
	QueryClientProvider,
	useQueryClient,
} from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { type ReactNode, useState } from "react";
import { expect, vi } from "vitest";
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

type Route = () => Response | Promise<Response>;

// Routes are keyed "METHOD /path". An unrouted request fails the test instead of answering.
export function stubFetch(routes: Record<string, Route>) {
	const fetchMock = vi.fn(async (request: Request) => {
		const key = `${request.method} ${new URL(request.url).pathname}`;
		const route = routes[key];
		if (route === undefined) {
			throw new Error(`Unexpected request: ${key}`);
		}
		return route();
	});
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
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
