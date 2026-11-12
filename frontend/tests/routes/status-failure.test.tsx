import { fireEvent, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { errorBody, fakeAuthBackend, stubFetch } from "../helpers/auth-api";
import { renderApp } from "../helpers/render-app";

const statusKey = "GET /api/v1/auth/status";
const credentials = { username: "admin", password: "fake-password-1" };

async function alertText() {
	return (await screen.findByRole("alert")).textContent;
}

test("a failing status request shows what happened and what to do, not the router's default", async () => {
	stubFetch({
		[statusKey]: () =>
			Response.json(errorBody("internal_error"), { status: 502 }),
	});

	renderApp("/");

	expect(await alertText()).toBe(
		"Tomarr answered with status 502. Try again, and check the Tomarr log if it keeps happening.",
	);
	expect(document.body.textContent).not.toContain("Something went wrong");
	expect(document.body.textContent).not.toContain("!");
});

test("an unreachable backend says Tomarr could not be reached", async () => {
	stubFetch({
		[statusKey]: () => {
			throw new TypeError("Failed to fetch");
		},
	});

	renderApp("/");

	expect(await alertText()).toBe(
		"Could not reach Tomarr. Check that it is running, then try again.",
	);
});

test("an answer that is not an auth status says the page could not read it", async () => {
	stubFetch({
		[statusKey]: () => Response.json({ hello: "proxy page" }),
	});

	renderApp("/");

	expect(await alertText()).toBe(
		"Tomarr sent an answer the page could not read. Reload the page, and check the Tomarr log if it keeps happening.",
	);
});

test("Try again asks the backend again and lands in the app once it answers", async () => {
	let backendUp = false;
	const backend = fakeAuthBackend({ credentials, signedIn: true });
	stubFetch({
		...backend.routes,
		[statusKey]: (request) =>
			backendUp
				? backend.routes[statusKey](request)
				: Response.json(errorBody("internal_error"), { status: 502 }),
	});

	renderApp("/");
	await alertText();
	backendUp = true;
	fireEvent.click(screen.getByRole("button", { name: "Try again" }));

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
});
