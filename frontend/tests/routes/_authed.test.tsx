import { QueryClient } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import {
	authStatusKey,
	authStatusQueryOptions,
	refetchAuthStatus,
} from "@/api/use-auth-status";
import { fakeAuthBackend, requestsTo, stubFetch } from "../helpers/auth-api";
import { renderApp } from "../helpers/render-app";

const credentials = { username: "admin", password: "fake-password-1" };

test("a fresh install sends the visitor to sign-up", async () => {
	stubFetch(fakeAuthBackend().routes);

	const router = renderApp("/");

	expect(await screen.findByRole("heading", { name: "Sign up" })).toBeDefined();
	expect(router.state.location.pathname).toBe("/sign-up");
});

test("a visitor who is not signed in goes to sign-in with the requested path", async () => {
	stubFetch(fakeAuthBackend({ credentials }).routes);

	const router = renderApp("/");

	expect(await screen.findByRole("heading", { name: "Sign in" })).toBeDefined();
	expect(router.state.location.pathname).toBe("/sign-in");
	expect(router.state.location.search).toEqual({ redirect: "/" });
});

test("a status whose last refetch failed is fetched again instead of trusted", async () => {
	const queryClient = new QueryClient();
	stubFetch(fakeAuthBackend({ credentials }).routes);
	await queryClient.query(authStatusQueryOptions);
	stubFetch({
		"GET /api/v1/auth/status": () => {
			throw new TypeError("Failed to fetch");
		},
	});
	await refetchAuthStatus(queryClient);
	expect(queryClient.getQueryState(authStatusKey)).toMatchObject({
		status: "error",
		data: { authenticated: false },
	});
	stubFetch(fakeAuthBackend({ credentials, signedIn: true }).routes);

	const router = renderApp("/", queryClient);

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.pathname).toBe("/");
});

test("sign out posts to logout and lands on sign-in", async () => {
	const fetchMock = stubFetch(
		fakeAuthBackend({ credentials, signedIn: true }).routes,
	);
	const router = renderApp("/");
	await screen.findByText("Backend version 1.2.3");

	fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

	expect(await screen.findByRole("heading", { name: "Sign in" })).toBeDefined();
	expect(router.state.location.pathname).toBe("/sign-in");
	expect(requestsTo(fetchMock, "POST /api/v1/auth/logout")).toHaveLength(1);
});

test("a failed sign out says so and keeps the visitor in the app", async () => {
	const { routes } = fakeAuthBackend({ credentials, signedIn: true });
	stubFetch({
		...routes,
		"POST /api/v1/auth/logout": () => {
			throw new TypeError("Failed to fetch");
		},
	});
	const router = renderApp("/");
	await screen.findByText("Backend version 1.2.3");

	fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

	await waitFor(() =>
		expect(screen.getByRole("alert").textContent).toBe(
			"Could not reach Tomarr. Check that it is running, then try again.",
		),
	);
	expect(router.state.location.pathname).toBe("/");
});
