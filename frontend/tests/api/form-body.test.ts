import { expect, test, vi } from "vitest";
import { client } from "@/api/client";
import { formBody } from "@/api/form-body";

async function postLogin(username: string, password: string) {
	const fetchMock = vi
		.fn()
		.mockResolvedValue(new Response(null, { status: 204 }));
	vi.stubGlobal("fetch", fetchMock);
	await client.POST("/api/v1/auth/login", {
		...formBody,
		body: { username, password },
	});
	const request: Request = fetchMock.mock.calls[0]?.[0];
	return request;
}

test("sends the body as a urlencoded form, not JSON", async () => {
	const request = await postLogin("admin", "secret");

	expect(request.headers.get("content-type")).toBe(
		"application/x-www-form-urlencoded",
	);
	expect(await request.text()).toBe("username=admin&password=secret");
});

test.each([
	["plus and ampersand", "a+b&c"],
	["equals and percent", "x=1%20y"],
	["spaces", "  two  spaces  "],
	["quotes", `"double" and 'single'`],
	["non-ASCII", "pässwörd 密码 🔑"],
])("round-trips a password with %s", async (_, password) => {
	const request = await postLogin("ユーザー & co", password);

	const parsed = new URLSearchParams(await request.text());
	expect([...parsed.entries()]).toEqual([
		["username", "ユーザー & co"],
		["password", password],
	]);
});
