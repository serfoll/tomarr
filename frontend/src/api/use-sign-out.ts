import { useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/api/client";
import { apiErrorFrom } from "@/api/errors";
import { refetchAuthStatus } from "@/api/use-auth-status";

async function signOut() {
	const { error, response } = await client.POST("/api/v1/auth/logout");
	if (!response.ok) {
		throw apiErrorFrom(response.status, error);
	}
}

export function useSignOut() {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: signOut,
		onSuccess: () => refetchAuthStatus(queryClient),
	});
}
