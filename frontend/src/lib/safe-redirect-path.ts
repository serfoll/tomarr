// A same-origin path starts with exactly one slash. "//host" and "/\host" are read by browsers as another host.
const sameOriginPath = /^\/(?![/\\])/;
const controlCharacter = /\p{Cc}/u;

export function safeRedirectPath(value: unknown): string {
	if (
		typeof value === "string" &&
		sameOriginPath.test(value) &&
		!controlCharacter.test(value)
	) {
		return value;
	}
	return "/";
}
