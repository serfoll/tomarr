import { type FormEvent, useState } from "react";
import { ApiError } from "@/api/errors";
import { useSignUp } from "@/api/use-sign-up";
import { CredentialFields } from "@/components/credential-fields";
import {
	credentialsNotAcceptedText,
	requestErrorText,
} from "@/lib/request-error-text";

interface SignUpFormProps {
	passwordMinLength: number;
	onSignedUp: () => void;
	onPasswordAlreadySet: () => void;
}

export function SignUpForm({
	passwordMinLength,
	onSignedUp,
	onPasswordAlreadySet,
}: SignUpFormProps) {
	const signUp = useSignUp();
	const [username, setUsername] = useState("");
	const [password, setPassword] = useState("");
	const [confirmation, setConfirmation] = useState("");
	const [message, setMessage] = useState("");

	function problemBeforeSending() {
		if (username.trim() === "") {
			return "Enter a username.";
		}
		// The server counts code points, and an emoji is two UTF-16 units in .length.
		if ([...password].length < passwordMinLength) {
			return `Choose a password of at least ${passwordMinLength} characters.`;
		}
		if (password !== confirmation) {
			return "The passwords do not match. Type the same password in both fields.";
		}
		return "";
	}

	function submit(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		const problem = problemBeforeSending();
		setMessage(problem);
		if (problem !== "") {
			return;
		}
		signUp.mutate(
			{ username, password },
			{
				onSuccess: onSignedUp,
				onError: (error) => {
					if (error instanceof ApiError && error.status === 409) {
						onPasswordAlreadySet();
						return;
					}
					setMessage(
						requestErrorText(error, { 400: credentialsNotAcceptedText }),
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
				passwordAutoComplete="new-password"
				onUsernameChange={setUsername}
				onPasswordChange={setPassword}
			/>
			<label>
				Confirm password
				<input
					name="confirmation"
					type="password"
					autoComplete="new-password"
					value={confirmation}
					onChange={(event) => setConfirmation(event.target.value)}
				/>
			</label>
			{message !== "" && <p role="alert">{message}</p>}
			<button type="submit" disabled={signUp.isPending}>
				Sign up
			</button>
		</form>
	);
}
