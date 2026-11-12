import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { BackendVersion } from "@/components/backend-version";

function renderBackendVersion() {
	render(
		<QueryClientProvider client={new QueryClient()}>
			<BackendVersion />
		</QueryClientProvider>,
	);
}

test("shows a loading state, then the backend version", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(Response.json({ version: "1.2.3" })),
	);

	renderBackendVersion();

	expect(screen.getByText("Loading the backend version.")).toBeDefined();
	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
});

test("asks the user to sign in on a 401", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
	);

	renderBackendVersion();

	expect(
		await screen.findByText(
			"You are not signed in. Sign in to see the backend version.",
		),
	).toBeDefined();
});

test("says Tomarr is unreachable when the request fails", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
	);

	renderBackendVersion();

	expect(
		await screen.findByText(
			"Could not reach Tomarr. Check that it is running, then reload.",
		),
	).toBeDefined();
});

test("names the status and what to do for any other failure", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(new Response(null, { status: 500 })),
	);

	renderBackendVersion();

	expect(
		await screen.findByText(
			"Tomarr answered with status 500. Reload the page, and check the Tomarr log if it keeps happening.",
		),
	).toBeDefined();
});

test("says the answer could not be read when the body is not a status", async () => {
	vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(null)));

	renderBackendVersion();

	expect(
		await screen.findByText(
			"Tomarr sent an answer the page could not read. Reload the page, and check the Tomarr log if it keeps happening.",
		),
	).toBeDefined();
});
