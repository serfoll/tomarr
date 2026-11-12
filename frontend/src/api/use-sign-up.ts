import { useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/api/client";
import { apiErrorFrom } from "@/api/errors";
import { type Credentials, formBody } from "@/api/form-body";
import { refetchAuthStatus } from "@/api/use-auth-status";

async function signUp(credentials: Credentials) {
	const { error, response } = await client.POST("/api/v1/auth/setup", {
		...formBody,
		body: credentials,
	});
	if (!response.ok) {
		throw apiErrorFrom(response.status, error);
	}
}

export function useSignUp() {
	const queryClient = useQueryClient();
	return useMutation({
		gcTime: 0,
		mutationFn: signUp,
		onSuccess: () => refetchAuthStatus(queryClient),
	});
}
