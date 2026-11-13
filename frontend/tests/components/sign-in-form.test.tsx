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

test("two submits before the first answers send one login request", async () => {
	const backend = fakeAuthBackend({ credentials });
	const held = heldRoute(backend.routes[loginKey]);
	const { fetchMock } = await openSignIn("/sign-in", {
		...backend.routes,
		[loginKey]: held.route,
	});
	fillIn("Username", credentials.username);
	fillIn("Password", credentials.password);
	const form = screen.getByRole("button", { name: "Sign in" }).closest("form");

	fireEvent.submit(form as HTMLFormElement);
	fireEvent.submit(form as HTMLFormElement);
	held.release();

	await screen.findByRole("heading", { name: "Tomarr" });
	expect(requestsTo(fetchMock, loginKey)).toHaveLength(1);
});

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

const resetHint =
	"Forgot your password? The Tomarr documentation explains how to reset it.";

test("the reset hint is absent after no failures and after one wrong password", async () => {
	await openSignIn();
	expect(screen.queryByText(resetHint)).toBeNull();

	submit("fake-wrong-password");
	await screen.findByRole("alert");

	expect(screen.queryByText(resetHint)).toBeNull();
});

test("two wrong passwords in a row show the reset hint as a plain paragraph", async () => {
	await openSignIn();

	submit("fake-wrong-password");
	await screen.findByRole("alert");
	submit("fake-wrong-password");

	const hint = await screen.findByText(resetHint);
	expect(hint.tagName).toBe("P");
	expect(hint.getAttribute("role")).toBeNull();
	expect(hint.textContent).not.toContain("TOMARR");
	expect(screen.getAllByRole("alert")).toHaveLength(1);
});

test("the reset hint stays after a third wrong password", async () => {
	await openSignIn();

	for (let attempt = 0; attempt < 3; attempt++) {
		submit("fake-wrong-password");
		await waitFor(() =>
			expect(screen.getByLabelText<HTMLInputElement>("Password").value).toBe(
				"",
			),
		);
	}

	expect(screen.getByText(resetHint)).toBeDefined();
});

test.each([
	{
		name: "400s",
		answer: () =>
			Response.json(errorBody("validation_failed"), { status: 400 }),
	},
	{
		name: "network failures",
		answer: () => {
			throw new TypeError("Failed to fetch");
		},
	},
	{
		name: "500s",
		answer: () => Response.json(errorBody("internal_error"), { status: 500 }),
	},
])("two $name do not show the reset hint", async ({ answer }) => {
	const { routes } = fakeAuthBackend({ credentials });
	const { fetchMock } = await openSignIn("/sign-in", {
		...routes,
		[loginKey]: answer,
	});

	submit();
	await waitFor(() => expect(requestsTo(fetchMock, loginKey)).toHaveLength(1));
	await screen.findByRole("alert");
	submit();
	await waitFor(() => expect(requestsTo(fetchMock, loginKey)).toHaveLength(2));
	await screen.findByRole("alert");

	expect(screen.queryByText(resetHint)).toBeNull();
});

test("a wrong password and a server error do not add up to the reset hint", async () => {
	const backend = fakeAuthBackend({ credentials });
	let failWithServerError = false;
	const { fetchMock } = await openSignIn("/sign-in", {
		...backend.routes,
		[loginKey]: (request) =>
			failWithServerError
				? Response.json(errorBody("internal_error"), { status: 500 })
				: backend.routes[loginKey](request),
	});

	submit("fake-wrong-password");
	await waitFor(() => expect(requestsTo(fetchMock, loginKey)).toHaveLength(1));
	failWithServerError = true;
	submit();
	await waitFor(() => expect(requestsTo(fetchMock, loginKey)).toHaveLength(2));
	await screen.findByText(/status 500/);

	expect(screen.queryByText(resetHint)).toBeNull();
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
	expect(router.state.location.search).toEqual({ redirect: "/" });

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
