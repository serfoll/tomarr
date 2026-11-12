import { ApiError } from "@/api/errors";

export const credentialsNotAcceptedText =
	"The username or password was not accepted. Check both and try again.";

// Texts for statuses the caller knows about come first, then the wording every request shares.
export function requestErrorText(
	error: Error,
	textByStatus: Record<number, string> = {},
): string {
	if (!(error instanceof ApiError)) {
		return "Could not reach Tomarr. Check that it is running, then try again.";
	}
	return (
		textByStatus[error.status] ??
		`Tomarr answered with status ${error.status}. Try again, and check the Tomarr log if it keeps happening.`
	);
}
