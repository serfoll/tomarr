import { QueryClientProvider } from "@tanstack/react-query";
import {
	createMemoryHistory,
	createRouter,
	RouterProvider,
} from "@tanstack/react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { createQueryClient } from "@/api/query-client";
import { routeTree } from "@/routeTree.gen";

export function fillIn(label: string, value: string) {
	fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

export function renderApp(path: string, queryClient = createQueryClient()) {
	const router = createRouter({
		routeTree,
		context: { queryClient },
		history: createMemoryHistory({ initialEntries: [path] }),
	});
	render(
		<QueryClientProvider client={queryClient}>
			<RouterProvider router={router} />
		</QueryClientProvider>,
	);
	return router;
}
