import { expect, test, vi } from "vitest";
import { client } from "@/api/client";

test("sends through a fetch stubbed after the client module loaded", async () => {
	const fetchMock = vi
		.fn()
		.mockResolvedValue(Response.json({ version: "1.2.3" }));
	vi.stubGlobal("fetch", fetchMock);

	const { data } = await client.GET("/api/v1/system/status");

	expect(fetchMock).toHaveBeenCalledTimes(1);
	expect(data).toEqual({ version: "1.2.3" });
});
