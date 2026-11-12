import { expect, test } from "vitest";
import { apiProxy } from "../vite-proxy";

test("the /api proxy adds X-Api-Key when a dev key is set", () => {
	expect(apiProxy("fake-dev-key")).toEqual({
		"/api": {
			target: "http://127.0.0.1:8000",
			headers: { "X-Api-Key": "fake-dev-key" },
		},
	});
});

test("the /api proxy adds no header without a dev key", () => {
	expect(apiProxy(undefined)).toEqual({
		"/api": { target: "http://127.0.0.1:8000" },
	});
});
