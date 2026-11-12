import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { createQueryClient } from "@/api/query-client";
import { fakeAuthBackend, stubFetch } from "../helpers/auth-api";
import { fillIn, renderApp } from "../helpers/render-app";

const credentials = { username: "admin", password: "fake-password-1" };
const systemStatusKey = ["system", "status"];

test("sign-out drops the data of the signed-in visitor from the cache", async () => {
	const queryClient = createQueryClient();
	stubFetch(fakeAuthBackend({ credentials, signedIn: true }).routes);
	renderApp("/", queryClient);
	await screen.findByText("Backend version 1.2.3");

	fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

	await screen.findByRole("heading", { name: "Sign in" });
	expect(queryClient.getQueryData(systemStatusKey)).toBeUndefined();
});

test("a 401 on a query sends the visitor to sign-in with the page they were on", async () => {
	const queryClient = createQueryClient();
	const backend = fakeAuthBackend({ credentials, signedIn: true });
	stubFetch(backend.routes);
	const router = renderApp("/", queryClient);
	await screen.findByText("Backend version 1.2.3");

	backend.state.signedIn = false;
	await queryClient.refetchQueries({ queryKey: systemStatusKey });

	await screen.findByRole("heading", { name: "Sign in" });
	expect(router.state.location.pathname).toBe("/sign-in");
	expect(router.state.location.search).toEqual({ redirect: "/" });
	expect(queryClient.getQueryData(systemStatusKey)).toBeUndefined();
});

test("a 401 does not sign out a visitor the backend still knows", async () => {
	const queryClient = createQueryClient();
	const backend = fakeAuthBackend({ credentials, signedIn: true });
	stubFetch({
		...backend.routes,
		"GET /api/v1/system/status": () =>
			Response.json(
				{ code: "not_authenticated", message: "No.", request_id: "abc123" },
				{ status: 401 },
			),
	});
	const router = renderApp("/", queryClient);

	expect(await screen.findByRole("alert")).toBeDefined();
	await waitFor(() => expect(router.state.status).toBe("idle"));
	expect(router.state.location.pathname).toBe("/");
});

test("the password does not stay in the mutation cache after sign-in", async () => {
	const queryClient = createQueryClient();
	stubFetch(fakeAuthBackend({ credentials }).routes);
	renderApp("/sign-in", queryClient);
	await screen.findByRole("heading", { name: "Sign in" });
	fillIn("Username", credentials.username);
	fillIn("Password", credentials.password);

	fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

	await screen.findByRole("heading", { name: "Tomarr" });
	await waitFor(() =>
		expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
	);
});

test("the password does not stay in the mutation cache after sign-up", async () => {
	const queryClient = createQueryClient();
	stubFetch(fakeAuthBackend().routes);
	renderApp("/sign-up", queryClient);
	await screen.findByRole("heading", { name: "Sign up" });
	fillIn("Username", credentials.username);
	fillIn("Password", credentials.password);
	fillIn("Confirm password", credentials.password);

	fireEvent.click(screen.getByRole("button", { name: "Sign up" }));

	await screen.findByRole("heading", { name: "Tomarr" });
	await waitFor(() =>
		expect(queryClient.getMutationCache().getAll()).toHaveLength(0),
	);
});
