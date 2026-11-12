import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { ensureAuthStatus } from "@/api/use-auth-status";
import { SignOutButton } from "@/components/sign-out-button";

export const Route = createFileRoute("/_authed")({
	beforeLoad: async ({ context, location }) => {
		const status = await ensureAuthStatus(context.queryClient);
		if (status.setup_required) {
			throw redirect({ to: "/sign-up" });
		}
		if (!status.authenticated) {
			throw redirect({ to: "/sign-in", search: { redirect: location.href } });
		}
	},
	component: AuthedLayout,
});

function AuthedLayout() {
	return (
		<>
			<SignOutButton />
			<Outlet />
		</>
	);
}
