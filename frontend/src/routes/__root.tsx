import type { QueryClient } from "@tanstack/react-query";
import {
	createRootRouteWithContext,
	type ErrorComponentProps,
	Outlet,
	useRouter,
} from "@tanstack/react-router";
import { requestErrorText } from "@/lib/request-error-text";

interface RouterContext {
	queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
	component: RootLayout,
	errorComponent: RootError,
});

function RootLayout() {
	return (
		<main>
			<Outlet />
		</main>
	);
}

// A route guard that cannot read the auth status throws before any page renders, so this is all the visitor sees.
function RootError({ error }: ErrorComponentProps) {
	const router = useRouter();

	return (
		<main>
			<h1>Tomarr could not load</h1>
			<p role="alert">{requestErrorText(error)}</p>
			<button type="button" onClick={() => router.invalidate()}>
				Try again
			</button>
		</main>
	);
}
