import { spawnSync } from "node:child_process";
import {
	appendFileSync,
	copyFileSync,
	mkdirSync,
	mkdtempSync,
	readdirSync,
	readFileSync,
	rmSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, expect, test } from "vitest";

// Vitest runs from frontend/, and jsdom gives import.meta.url a non-file scheme.
const script = join(process.cwd(), "scripts/gen-api.sh");
const committed = join(process.cwd(), "src/api/schema.gen.ts");
// Each run starts uv and the schema dump, so it takes a few seconds.
const RUN_TIMEOUT_MS = 60_000;

let workDir: string;
let target: string;
let tempRoot: string;

beforeEach(() => {
	workDir = mkdtempSync(join(tmpdir(), "gen-api-test-"));
	target = join(workDir, "schema.gen.ts");
	tempRoot = join(workDir, "tmp");
	mkdirSync(tempRoot);
	copyFileSync(committed, target);
});

afterEach(() => {
	rmSync(workDir, { recursive: true, force: true });
});

// uv keeps its own lock file in TMPDIR, so only the script's directories count.
function leftoverTempEntries() {
	return readdirSync(tempRoot).filter((name) => !name.startsWith("uv-"));
}

function run(args: string[], env: Record<string, string> = {}) {
	return spawnSync("bash", [script, ...args], {
		encoding: "utf8",
		env: {
			...process.env,
			TOMARR_GEN_API_TARGET: target,
			TMPDIR: tempRoot,
			...env,
		},
	});
}

test(
	"--check exits 0 when the file matches a fresh generation",
	() => {
		expect(run(["--check"]).status).toBe(0);
	},
	RUN_TIMEOUT_MS,
);

test(
	"--check fails and says to run pnpm gen:api when the file is stale",
	() => {
		appendFileSync(target, "// stale\n");

		const result = run(["--check"]);

		expect(result.status).not.toBe(0);
		expect(result.stderr).toContain("pnpm gen:api");
	},
	RUN_TIMEOUT_MS,
);

test(
	"--check leaves the file unchanged and removes its temp directory",
	() => {
		appendFileSync(target, "// stale\n");
		const before = readFileSync(target, "utf8");

		run(["--check"]);

		expect(readFileSync(target, "utf8")).toBe(before);
		expect(leftoverTempEntries()).toEqual([]);
	},
	RUN_TIMEOUT_MS,
);

test(
	"without a flag it rewrites a stale file to the fresh generation",
	() => {
		appendFileSync(target, "// stale\n");

		const result = run([]);

		expect(result.status).toBe(0);
		expect(readFileSync(target, "utf8")).toBe(readFileSync(committed, "utf8"));
	},
	RUN_TIMEOUT_MS,
);

test(
	"it exits non-zero and keeps the file when the backend command fails",
	() => {
		const before = readFileSync(target, "utf8");

		const result = run([], {
			TOMARR_GEN_API_BACKEND_DIR: join(workDir, "missing-backend"),
		});

		expect(result.status).not.toBe(0);
		expect(readFileSync(target, "utf8")).toBe(before);
		expect(leftoverTempEntries()).toEqual([]);
	},
	RUN_TIMEOUT_MS,
);

test(
	"--check says the file is missing, not out of date, when there is no committed file",
	() => {
		const result = run(["--check"], {
			TOMARR_GEN_API_TARGET: join(workDir, "missing.gen.ts"),
		});

		expect(result.status).toBe(1);
		expect(result.stderr).toContain("missing");
		expect(result.stderr).not.toContain("out of date");
	},
	RUN_TIMEOUT_MS,
);

test("an argument after the first is refused before anything runs", () => {
	const before = readFileSync(target, "utf8");

	const result = run(["--check", "--bogus"]);

	expect(result.status).toBe(2);
	expect(result.stderr).toContain("--bogus");
	expect(readFileSync(target, "utf8")).toBe(before);
	expect(leftoverTempEntries()).toEqual([]);
});
