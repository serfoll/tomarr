import { ApiError, UnreadableResponseError } from "@/api/errors";

export const credentialsNotAcceptedText =
	"The username or password was not accepted. Check both and try again.";

export const unreadableResponseText =
	"Tomarr sent an answer the page could not read. Reload the page, and check the Tomarr log if it keeps happening.";

// Texts for statuses the caller knows about come first, then the wording every request shares.
export function requestErrorText(
	error: unknown,
	textByStatus: Record<number, string> = {},
): string {
	if (error instanceof UnreadableResponseError) {
		return unreadableResponseText;
	}
	if (!(error instanceof ApiError)) {
		return "Could not reach Tomarr. Check that it is running, then try again.";
	}
	return (
		textByStatus[error.status] ??
		`Tomarr answered with status ${error.status}. Try again, and check the Tomarr log if it keeps happening.`
	);
}
