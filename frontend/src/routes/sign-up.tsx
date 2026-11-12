import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { ensureAuthStatus, refetchAuthStatus } from "@/api/use-auth-status";
import { SignUpForm } from "@/components/sign-up-form";

export const Route = createFileRoute("/sign-up")({
	beforeLoad: async ({ context }) => {
		const status = await ensureAuthStatus(context.queryClient);
		if (status.authenticated) {
			throw redirect({ to: "/" });
		}
		if (!status.setup_required) {
			throw redirect({ to: "/sign-in" });
		}
		return { passwordMinLength: status.password_min_length };
	},
	component: SignUpPage,
});

function SignUpPage() {
	const { passwordMinLength } = Route.useRouteContext();
	const navigate = Route.useNavigate();
	const queryClient = useQueryClient();

	// The cached status still says sign-up is open, and the sign-in guard would send the visitor straight back.
	async function goToSignIn() {
		await refetchAuthStatus(queryClient);
		await navigate({ to: "/sign-in", search: { passwordSet: true } });
	}

	return (
		<>
			<h1>Sign up</h1>
			<SignUpForm
				passwordMinLength={passwordMinLength}
				onSignedUp={() => navigate({ to: "/" })}
				onPasswordAlreadySet={goToSignIn}
			/>
		</>
	);
}
