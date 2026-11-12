interface CredentialFieldsProps {
	username: string;
	password: string;
	passwordAutoComplete: "new-password" | "current-password";
	onUsernameChange: (username: string) => void;
	onPasswordChange: (password: string) => void;
}

export function CredentialFields({
	username,
	password,
	passwordAutoComplete,
	onUsernameChange,
	onPasswordChange,
}: CredentialFieldsProps) {
	return (
		<>
			<label>
				Username
				<input
					name="username"
					autoComplete="username"
					value={username}
					onChange={(event) => onUsernameChange(event.target.value)}
				/>
			</label>
			<label>
				Password
				<input
					name="password"
					type="password"
					autoComplete={passwordAutoComplete}
					value={password}
					onChange={(event) => onPasswordChange(event.target.value)}
				/>
			</label>
		</>
	);
}
