#!/usr/bin/env bash
# Regenerates src/api/schema.gen.ts from the backend's OpenAPI schema.
# With --check it only compares and exits non-zero when the committed file is stale.
# TOMARR_GEN_API_BACKEND_DIR and TOMARR_GEN_API_TARGET override the backend project and the output file.
set -euo pipefail

frontend="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend="${TOMARR_GEN_API_BACKEND_DIR:-$frontend/../backend}"
target="${TOMARR_GEN_API_TARGET:-$frontend/src/api/schema.gen.ts}"

check=false
case "${1:-}" in
	"") ;;
	--check) check=true ;;
	*)
		echo "Unknown argument '$1'. Use no argument to regenerate or --check to compare." >&2
		exit 2
		;;
esac

tmp="$(mktemp -d "${TMPDIR:-/tmp}/gen-api.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

uv run --project "$backend" python -m tomarr.openapi > "$tmp/openapi.json"
"$frontend/node_modules/.bin/openapi-typescript" "$tmp/openapi.json" -o "$tmp/schema.gen.ts"

if [ "$check" = true ]; then
	if ! diff -q "$target" "$tmp/schema.gen.ts" > /dev/null; then
		echo "The generated API types are out of date. Run pnpm gen:api and commit the result." >&2
		exit 1
	fi
else
	cp "$tmp/schema.gen.ts" "$target"
fi
