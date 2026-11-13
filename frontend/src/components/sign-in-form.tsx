import { type FormEvent, useState } from "react";
import { ApiError } from "@/api/errors";
import { useSignIn } from "@/api/use-sign-in";
import { CredentialFields } from "@/components/credential-fields";
import {
	credentialsNotAcceptedText,
	requestErrorText,
} from "@/lib/request-error-text";

const wrongPasswordsBeforeResetHint = 2;

interface SignInFormProps {
	onSignedIn: () => void;
}

export function SignInForm({ onSignedIn }: SignInFormProps) {
	const signIn = useSignIn();
	const [username, setUsername] = useState("");
	const [password, setPassword] = useState("");
	const [message, setMessage] = useState("");
	const [wrongPasswordCount, setWrongPasswordCount] = useState(0);

	function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (signIn.isPending) {
			return;
		}
		setMessage("");
		signIn.mutate(
			{ username, password },
			{
				onSuccess: onSignedIn,
				onError: (error) => {
					if (error instanceof ApiError && error.status === 401) {
						setPassword("");
						setWrongPasswordCount((count) => count + 1);
					}
					setMessage(
						requestErrorText(error, {
							400: credentialsNotAcceptedText,
							401: "Wrong username or password. Check both and try again.",
						}),
					);
				},
			},
		);
	}

	return (
		<form onSubmit={submit} noValidate>
			<CredentialFields
				username={username}
				password={password}
				passwordAutoComplete="current-password"
				onUsernameChange={setUsername}
				onPasswordChange={setPassword}
			/>
			{message !== "" && <p role="alert">{message}</p>}
			{wrongPasswordCount >= wrongPasswordsBeforeResetHint && (
				<p>
					Forgot your password? The Tomarr documentation explains how to reset
					it.
				</p>
			)}
			<button type="submit" disabled={signIn.isPending}>
				Sign in
			</button>
		</form>
	);
}
