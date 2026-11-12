import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
	createFileRoute,
	Outlet,
	redirect,
	useRouter,
} from "@tanstack/react-router";
import { useEffect } from "react";
import {
	authStatusQueryOptions,
	dropPrivateQueries,
	ensureAuthStatus,
} from "@/api/use-auth-status";
import { SignOutButton } from "@/components/sign-out-button";

export const Route = createFileRoute("/_authed")({
	beforeLoad: async ({ context, location }) => {
		const status = await ensureAuthStatus(context.queryClient);
		if (status.authenticated) {
			return;
		}
		if (status.setup_required) {
			throw redirect({ to: "/sign-up" });
		}
		throw redirect({ to: "/sign-in", search: { redirect: location.href } });
	},
	component: AuthedLayout,
});

function AuthedLayout() {
	const router = useRouter();
	const queryClient = useQueryClient();
	// A static stale time would exempt the status from the refetch that follows sign-out and a 401.
	const status = useQuery({ ...authStatusQueryOptions, refetchOnMount: false });
	const signedOut = status.data !== undefined && !status.data.authenticated;

	// Sign-out and an ended session both land here once the status is refetched, and the guard picks the page.
	useEffect(() => {
		if (signedOut) {
			dropPrivateQueries(queryClient);
			void router.invalidate();
		}
	}, [signedOut, queryClient, router]);

	return (
		<>
			<SignOutButton />
			<Outlet />
		</>
	);
}
