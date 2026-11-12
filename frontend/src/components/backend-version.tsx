import { ApiError, UnreadableResponseError } from "@/api/errors";
import { useSystemStatus } from "@/api/use-system-status";
import { unreadableResponseText } from "@/lib/request-error-text";

function errorText(error: Error): string {
	if (error instanceof UnreadableResponseError) {
		return unreadableResponseText;
	}
	if (!(error instanceof ApiError)) {
		return "Could not reach Tomarr. Check that it is running, then reload.";
	}
	if (error.status === 401) {
		return "You are not signed in. Sign in to see the backend version.";
	}
	return `Tomarr answered with status ${error.status}. Reload the page, and check the Tomarr log if it keeps happening.`;
}

export function BackendVersion() {
	const status = useSystemStatus();

	if (status.isPending) {
		return <p>Loading the backend version.</p>;
	}
	if (status.isError) {
		return <p role="alert">{errorText(status.error)}</p>;
	}
	return <p>{`Backend version ${status.data.version}`}</p>;
}
