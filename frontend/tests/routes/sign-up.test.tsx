import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { fakeAuthBackend, stubFetch } from "../helpers/auth-api";
import { renderApp } from "../helpers/render-app";

const credentials = { username: "admin", password: "fake-password-1" };

test("sign-up is not offered once credentials exist", async () => {
	stubFetch(fakeAuthBackend({ credentials }).routes);

	const router = renderApp("/sign-up");

	expect(await screen.findByRole("heading", { name: "Sign in" })).toBeDefined();
	expect(router.state.location.pathname).toBe("/sign-in");
});

test("a signed-in visitor on sign-up lands in the app", async () => {
	stubFetch(fakeAuthBackend({ credentials, signedIn: true }).routes);

	const router = renderApp("/sign-up");

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.pathname).toBe("/");
});
