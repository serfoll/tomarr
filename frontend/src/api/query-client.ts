import { QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/errors";
import { authStatusKey, refetchAuthStatus } from "@/api/use-auth-status";

// A 401 on any other query means the session ended while the page was open. The refetched status tells the layout to leave.
export function createQueryClient() {
	const queryClient: QueryClient = new QueryClient({
		queryCache: new QueryCache({
			onError: (error, query) => {
				if (
					error instanceof ApiError &&
					error.status === 401 &&
					query.queryKey[0] !== authStatusKey[0]
				) {
					void refetchAuthStatus(queryClient);
				}
			},
		}),
	});
	return queryClient;
}
