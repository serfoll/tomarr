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

const loginKey = "POST /api/v1/auth/login";
const credentials = { username: "admin", password: "fake-password-1" };

async function openSignIn(
	path = "/sign-in",
	routes = fakeAuthBackend({ credentials }).routes,
) {
	const fetchMock = stubFetch(routes);
	const router = renderApp(path);
	await screen.findByRole("heading", { name: "Sign in" });
	return { fetchMock, router };
}

function submit(password = credentials.password) {
	fillIn("Username", credentials.username);
	fillIn("Password", password);
	fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

test("labels the fields with the autocomplete hints a password manager reads", async () => {
	await openSignIn();

	expect(screen.getByLabelText("Username").getAttribute("autocomplete")).toBe(
		"username",
	);
	expect(screen.getByLabelText("Password").getAttribute("autocomplete")).toBe(
		"current-password",
	);
});

test("a wrong password shows an alert, keeps the username and clears the password", async () => {
	const { fetchMock, router } = await openSignIn();

	submit("fake-wrong-password");

	expect((await screen.findByRole("alert")).textContent).toBe(
		"Wrong username or password. Check both and try again.",
	);
	expect(router.state.location.pathname).toBe("/sign-in");
	expect(screen.getByLabelText<HTMLInputElement>("Username").value).toBe(
		"admin",
	);
	expect(screen.getByLabelText<HTMLInputElement>("Password").value).toBe("");
	const [request] = requestsTo(fetchMock, loginKey);
	expect(
		Object.fromEntries(new URLSearchParams(await request?.text())),
	).toEqual({ username: "admin", password: "fake-wrong-password" });
});

test("signing in follows a safe redirect", async () => {
	const { router } = await openSignIn(
		`/sign-in?redirect=${encodeURIComponent("/?from=link")}`,
	);

	submit();

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.href).toBe("/?from=link");
});

test("signing in with a redirect to another host lands on the app root", async () => {
	const { router } = await openSignIn(
		`/sign-in?redirect=${encodeURIComponent("//evil.com")}`,
	);

	submit();

	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.href).toBe("/");
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
		answer: () => Response.json(errorBody("internal_error"), { status: 500 }),
		text: "Tomarr answered with status 500. Try again, and check the Tomarr log if it keeps happening.",
	},
])(
	"$name shows its message, stays on sign-in and keeps the password",
	async ({ answer, text }) => {
		const { routes } = fakeAuthBackend({ credentials });
		const { router } = await openSignIn("/sign-in", {
			...routes,
			[loginKey]: answer,
		});

		submit();

		expect((await screen.findByRole("alert")).textContent).toBe(text);
		expect(router.state.location.pathname).toBe("/sign-in");
		expect(screen.getByLabelText<HTMLInputElement>("Password").value).toBe(
			credentials.password,
		);
	},
);

test("the button is disabled while the request is in flight", async () => {
	const { routes } = fakeAuthBackend({ credentials });
	const held = heldRoute(routes[loginKey]);
	await openSignIn("/sign-in", { ...routes, [loginKey]: held.route });

	submit();

	const button = screen.getByRole("button", { name: "Sign in" });
	await waitFor(() => expect(button.hasAttribute("disabled")).toBe(true));
	held.release();
	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
});
