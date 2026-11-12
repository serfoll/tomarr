import { createFileRoute, redirect } from "@tanstack/react-router";
import { ensureAuthStatus } from "@/api/use-auth-status";
import { SignInForm } from "@/components/sign-in-form";
import { safeRedirectPath } from "@/lib/safe-redirect-path";

interface SignInSearch {
	redirect?: string;
	passwordSet?: boolean;
}

export const Route = createFileRoute("/sign-in")({
	validateSearch: (search: Record<string, unknown>) => {
		const valid: SignInSearch = {};
		if (search.redirect !== undefined) {
			valid.redirect = safeRedirectPath(search.redirect);
		}
		if (search.passwordSet === true) {
			valid.passwordSet = true;
		}
		return valid;
	},
	beforeLoad: async ({ context }) => {
		const status = await ensureAuthStatus(context.queryClient);
		if (status.setup_required) {
			throw redirect({ to: "/sign-up" });
		}
		if (status.authenticated) {
			throw redirect({ to: "/" });
		}
	},
	component: SignInPage,
});

function SignInPage() {
	const search = Route.useSearch();
	const navigate = Route.useNavigate();

	return (
		<>
			<h1>Sign in</h1>
			{search.passwordSet && <p>A password is already set. Sign in instead.</p>}
			<SignInForm
				onSignedIn={() => navigate({ href: safeRedirectPath(search.redirect) })}
			/>
		</>
	);
}
