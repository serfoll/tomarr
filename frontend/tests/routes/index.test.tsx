import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
	createMemoryHistory,
	createRouter,
	RouterProvider,
} from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { routeTree } from "@/routeTree.gen";

test("the index route shows the backend version", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(Response.json({ version: "1.2.3" })),
	);
	const router = createRouter({
		routeTree,
		history: createMemoryHistory({ initialEntries: ["/"] }),
	});

	render(
		<QueryClientProvider client={new QueryClient()}>
			<RouterProvider router={router} />
		</QueryClientProvider>,
	);

	expect(await screen.findByRole("heading", { name: "Tomarr" })).toBeDefined();
	expect(await screen.findByText("Backend version 1.2.3")).toBeDefined();
});
