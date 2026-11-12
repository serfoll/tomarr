import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useSignOut } from "@/api/use-sign-out";
import { requestErrorText } from "@/lib/request-error-text";

export function SignOutButton() {
	const signOut = useSignOut();
	const navigate = useNavigate();
	const [message, setMessage] = useState("");

	function click() {
		setMessage("");
		signOut.mutate(undefined, {
			onSuccess: () => navigate({ to: "/sign-in" }),
			onError: (error) => setMessage(requestErrorText(error)),
		});
	}

	return (
		<>
			<button type="button" onClick={click} disabled={signOut.isPending}>
				Sign out
			</button>
			{message !== "" && <p role="alert">{message}</p>}
		</>
	);
}
