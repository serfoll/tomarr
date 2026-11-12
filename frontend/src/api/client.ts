import createClient from "openapi-fetch";
import type { paths } from "@/api/schema.gen";

export const client = createClient<paths>({
	// Request needs an absolute URL outside a browser page, so the tests' Node Request rejects a bare path.
	baseUrl: window.location.origin,
	credentials: "same-origin",
	// openapi-fetch binds globalThis.fetch when the client is created, so a stub installed later would be missed.
	fetch: (request) => globalThis.fetch(request),
});
