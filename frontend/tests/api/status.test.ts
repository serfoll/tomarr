import { expect, test, vi } from "vitest";
import { getSystemStatus } from "@/api/status";

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
