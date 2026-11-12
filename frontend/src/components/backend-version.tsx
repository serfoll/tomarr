import { useQuery } from "@tanstack/react-query";
import { ApiError, getSystemStatus } from "@/api/status";

function errorText(error: Error): string {
	if (!(error instanceof ApiError)) {
		return "Could not reach Tomarr. Check that it is running, then reload.";
	}
	if (error.status === 401) {
		return "You are not signed in. Sign in to see the backend version.";
	}
	return `Tomarr answered with status ${error.status}. Reload the page, and check the Tomarr log if it keeps happening.`;
}

export function BackendVersion() {
	const status = useQuery({
		queryKey: ["system", "status"],
		queryFn: getSystemStatus,
		// Retrying cannot fix a 401 and would leave the loading text up for seconds.
		retry: false,
	});

	if (status.isPending) {
		return <p>Loading the backend version.</p>;
	}
	if (status.isError) {
		return <p role="alert">{errorText(status.error)}</p>;
	}
	return <p>{`Backend version ${status.data.version}`}</p>;
}
