import createClient from "openapi-fetch";
import type { paths } from "@/api/schema.gen";

export const client = createClient<paths>({
	// The Request constructor rejects a relative URL outside a browser page (jsdom and Node in tests), and the origin keeps requests same-origin in the real app.
	baseUrl: window.location.origin,
	credentials: "same-origin",
	// openapi-fetch binds globalThis.fetch when the client is created, so a stub installed after import would be missed.
	fetch: (request) => globalThis.fetch(request),
});
