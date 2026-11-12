import { useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/api/client";
import { apiErrorFrom } from "@/api/errors";
import { type Credentials, formBody } from "@/api/form-body";
import { refetchAuthStatus } from "@/api/use-auth-status";

async function signIn(credentials: Credentials) {
	const { error, response } = await client.POST("/api/v1/auth/login", {
		...formBody,
		body: credentials,
	});
	if (!response.ok) {
		throw apiErrorFrom(response.status, error);
	}
}

export function useSignIn() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: signIn,
		onSuccess: () => refetchAuthStatus(queryClient),
	});
}
