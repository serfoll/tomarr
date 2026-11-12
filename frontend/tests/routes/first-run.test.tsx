import { cleanup, fireEvent, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { fakeAuthBackend, stubFetch } from "../helpers/auth-api";
import { fillIn, renderApp } from "../helpers/render-app";

test("the first visit lands on sign-up, and a visit after sign-up and a lost session lands on sign-in", async () => {
	const backend = fakeAuthBackend();
	stubFetch(backend.routes);

	const firstVisit = renderApp("/");
	await screen.findByRole("heading", { name: "Sign up" });
	expect(firstVisit.state.location.pathname).toBe("/sign-up");

	fillIn("Username", "admin");
	fillIn("Password", "fake-password-1");
	fillIn("Confirm password", "fake-password-1");
	fireEvent.click(screen.getByRole("button", { name: "Sign up" }));

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(firstVisit.state.location.pathname).toBe("/");

	cleanup();
	backend.state.signedIn = false;

	const secondVisit = renderApp("/");

	expect(await screen.findByRole("heading", { name: "Sign in" })).toBeDefined();
	expect(secondVisit.state.location.pathname).toBe("/sign-in");
});
