import { UnreadableResponseError } from "@/api/errors";

// openapi-fetch parses a success body itself and a malformed one rejects with a SyntaxError.
// Only a SyntaxError raised after the response arrived is a body problem, so a failure inside fetch passes through.
export function trackResponse(unreadableMessage: string) {
	let responded = false;
	return {
		fetch: async (request: Request) => {
			const received = await globalThis.fetch(request);
			responded = true;
			return received;
		},
		// A network failure rejects with a TypeError and must stay that way.
		rethrow: (cause: unknown): never => {
			throw responded && cause instanceof SyntaxError
				? new UnreadableResponseError(unreadableMessage)
				: cause;
		},
	};
}
