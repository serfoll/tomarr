import { expect, test } from "vitest";
import { safeRedirectPath } from "@/lib/safe-redirect-path";

test.each(["/", "/series/1", "/series/1?tab=a#b"])(
	"keeps the same-origin path %s",
	(path) => {
		expect(safeRedirectPath(path)).toBe(path);
	},
);

test.each([
	["a protocol-relative URL", "//evil.com"],
	["a backslash host", "/\\evil.com"],
	["an absolute URL", "https://evil.com"],
	["a javascript URL", "javascript:alert(1)"],
	["an empty string", ""],
	["a path without a leading slash", "evil.com/path"],
	["a newline", "/series\n/1"],
	["a tab before a second slash", "/\t/evil.com"],
	["a carriage return", "/series\r1"],
	["a null byte", "/series\u00001"],
	["a delete character", "/series\u007f1"],
	["undefined", undefined],
	["null", null],
	["a number", 1],
	["an array", ["/series"]],
	["an object", { path: "/series" }],
])("falls back to / for %s", (_, value) => {
	expect(safeRedirectPath(value)).toBe("/");
});
