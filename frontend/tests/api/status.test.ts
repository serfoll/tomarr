import { expect, test, vi } from "vitest";
import { getSystemStatus, UnreadableResponseError } from "@/api/status";

test("requests the status same-origin with no extra headers", async () => {
	const fetchMock = vi
		.fn()
		.mockResolvedValue(Response.json({ version: "1.2.3" }));
	vi.stubGlobal("fetch", fetchMock);

	await expect(getSystemStatus()).resolves.toEqual({ version: "1.2.3" });
	expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/v1/system/status", {
		credentials: "same-origin",
	});
});

test.each([
	["null", () => Response.json(null)],
	["an empty object", () => Response.json({})],
	["a number version", () => Response.json({ version: 1 })],
	["an object version", () => Response.json({ version: { major: 1 } })],
	["an empty version", () => Response.json({ version: "" })],
	["invalid JSON", () => new Response("<html>proxy page</html>")],
	["a 204", () => new Response(null, { status: 204 })],
])("rejects a success response with %s as unreadable", async (_, response) => {
	vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response()));

	await expect(getSystemStatus()).rejects.toBeInstanceOf(
		UnreadableResponseError,
	);
});
