import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { fakeAuthBackend, stubFetch } from "../helpers/auth-api";
import { renderApp } from "../helpers/render-app";

test("the index route shows the backend version to a signed-in visitor", async () => {
	const { routes } = fakeAuthBackend({
		credentials: { username: "admin", password: "fake-password-1" },
		signedIn: true,
	});
	stubFetch(routes);

	const router = renderApp("/");

	expect(await screen.findByRole("heading", { name: "Tomarr" })).toBeDefined();
	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
	expect(router.state.location.pathname).toBe("/");
});
