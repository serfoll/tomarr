import { fireEvent, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import {
	errorBody,
	fakeAuthBackend,
	heldRoute,
	requestsTo,
	stubFetch,
} from "../helpers/auth-api";
import { fillIn, renderApp } from "../helpers/render-app";

const setupKey = "POST /api/v1/auth/setup";
const password = "fake-password-1";

async function openSignUp(routes = fakeAuthBackend().routes) {
	const fetchMock = stubFetch(routes);
	const router = renderApp("/sign-up");
	await screen.findByRole("heading", { name: "Sign up" });
	return { fetchMock, router };
}

function submit({
	username = "admin",
	confirmation = password,
	chosen = password,
} = {}) {
	fillIn("Username", username);
	fillIn("Password", chosen);
	fillIn("Confirm password", confirmation);
	fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
}

async function alertText() {
	return (await screen.findByRole("alert")).textContent;
}

test("labels the fields with the autocomplete hints a password manager reads", async () => {
	await openSignUp();

	expect(screen.getByLabelText("Username").getAttribute("autocomplete")).toBe(
		"username",
	);
	expect(screen.getByLabelText("Password").getAttribute("autocomplete")).toBe(
		"new-password",
	);
	expect(
		screen.getByLabelText("Confirm password").getAttribute("autocomplete"),
	).toBe("new-password");
});

test("a blank username shows a message and sends nothing", async () => {
	const { fetchMock } = await openSignUp();

	submit({ username: "   " });

	expect(await alertText()).toBe("Enter a username.");
	expect(requestsTo(fetchMock, setupKey)).toHaveLength(0);
});

test("a password shorter than the server's minimum shows that minimum and sends nothing", async () => {
	const { fetchMock } = await openSignUp(
		fakeAuthBackend({ passwordMinLength: 12 }).routes,
	);

	submit({ chosen: "elevenchars", confirmation: "elevenchars" });

	expect(await alertText()).toBe(
		"Choose a password of at least 12 characters.",
	);
	expect(requestsTo(fetchMock, setupKey)).toHaveLength(0);
});

test("the minimum counts characters as the server does, not UTF-16 units", async () => {
	const { fetchMock } = await openSignUp();
	const fourEmoji = "🔑🔑🔑🔑";

	submit({ chosen: fourEmoji, confirmation: fourEmoji });

	expect(await alertText()).toBe("Choose a password of at least 8 characters.");
	expect(requestsTo(fetchMock, setupKey)).toHaveLength(0);
});

test("a confirmation that does not match shows a message and sends nothing", async () => {
	const { fetchMock } = await openSignUp();

	submit({ confirmation: "fake-confirmation-2" });

	expect(await alertText()).toBe(
		"The passwords do not match. Type the same password in both fields.",
	);
	expect(requestsTo(fetchMock, setupKey)).toHaveLength(0);
	const bodies = await Promise.all(
		fetchMock.mock.calls.map(([request]) => request.clone().text()),
	);
	expect(bodies.join("")).not.toContain("fake-confirmation-2");
});

test("a valid sign-up posts only the username and password and lands in the app", async () => {
	const { fetchMock, router } = await openSignUp();

	submit();

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.pathname).toBe("/");
	const [request] = requestsTo(fetchMock, setupKey);
	expect(request?.headers.get("content-type")).toBe(
		"application/x-www-form-urlencoded",
	);
	expect(
		Object.fromEntries(new URLSearchParams(await request?.text())),
	).toEqual({ username: "admin", password });
});

test("a password set in the meantime sends the visitor to a plain sign-in form", async () => {
	const backend = fakeAuthBackend();
	const { router } = await openSignUp(backend.routes);
	backend.state.credentials = { username: "other", password: "fake-other-3" };

	submit();

	expect(await screen.findByRole("heading", { name: "Sign in" })).toBeDefined();
	expect(router.state.location.pathname).toBe("/sign-in");
	expect(router.state.location.search).toEqual({});
	expect(screen.queryByRole("paragraph")).toBeNull();
});

test.each([
	{
		name: "a 400",
		answer: () =>
			Response.json(errorBody("validation_failed"), { status: 400 }),
		text: "The username or password was not accepted. Check both and try again.",
	},
	{
		name: "a network failure",
		answer: () => {
			throw new TypeError("Failed to fetch");
		},
		text: "Could not reach Tomarr. Check that it is running, then try again.",
	},
	{
		name: "another status",
		answer: () => Response.json(errorBody("internal_error"), { status: 503 }),
		text: "Tomarr answered with status 503. Try again, and check the Tomarr log if it keeps happening.",
	},
])("$name shows its message and stays on sign-up", async ({ answer, text }) => {
	const { routes } = fakeAuthBackend();
	const { router } = await openSignUp({ ...routes, [setupKey]: answer });

	submit();

	expect(await alertText()).toBe(text);
	expect(router.state.location.pathname).toBe("/sign-up");
});

test("the button is disabled while the request is in flight", async () => {
	const { routes } = fakeAuthBackend();
	const held = heldRoute(routes[setupKey]);
	await openSignUp({ ...routes, [setupKey]: held.route });

	submit();

	const button = screen.getByRole("button", { name: "Sign up" });
	await waitFor(() => expect(button.hasAttribute("disabled")).toBe(true));
	held.release();
	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
});
