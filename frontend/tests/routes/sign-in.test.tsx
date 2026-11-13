import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { fakeAuthBackend, statusBody, stubFetch } from "../helpers/auth-api";
import { renderApp } from "../helpers/render-app";

test("sign-in on a fresh install sends the visitor to sign-up", async () => {
	stubFetch(fakeAuthBackend().routes);

	const router = renderApp("/sign-in");

	expect(await screen.findByRole("heading", { name: "Sign up" })).toBeDefined();
	expect(router.state.location.pathname).toBe("/sign-up");
});

test("a signed-in visitor on sign-in lands in the app", async () => {
	stubFetch(
		fakeAuthBackend({
			credentials: { username: "admin", password: "fake-password-1" },
			signedIn: true,
		}).routes,
	);

	const router = renderApp("/sign-in");

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.pathname).toBe("/");
});

test("a signed-in visitor on sign-in lands in the app while sign-up is reopened", async () => {
	const { routes } = fakeAuthBackend({
		credentials: { username: "admin", password: "fake-password-1" },
		signedIn: true,
	});
	stubFetch({
		...routes,
		"GET /api/v1/auth/status": () =>
			Response.json({ ...statusBody, setup_required: true }),
	});

	const router = renderApp("/sign-in");

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.pathname).toBe("/");
});
