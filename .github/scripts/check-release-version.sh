#!/usr/bin/env bash
# Usage: check-release-version.sh <tag> [pyproject-path]
# Exit 0: the tag is vMAJOR.MINOR.PATCH with an optional -suffix, and a stable tag matches the
# [project] version in pyproject.toml. A tag with a suffix skips the version comparison.
# Exit 1: the tag or the version is wrong. Exit 2: wrong arguments.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: check-release-version.sh <tag> [pyproject-path]" >&2
  exit 2
fi

tag="$1"
pyproject="${2:-backend/pyproject.toml}"

# A suffix identifier is 0, a number without a leading zero, or alphanumeric with at least one letter.
id='(0|[1-9][0-9]*|[0-9]*[A-Za-z][0-9A-Za-z]*)'
tag_re="^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-$id(\.$id)*)?\$"
if [[ ! "$tag" =~ $tag_re ]]; then
  echo "Release check failed: '$tag' is not a valid release tag. Use vMAJOR.MINOR.PATCH with an optional -suffix, for example v0.1.0 or v0.1.0-rc.1." >&2
  exit 1
fi

if [[ "$tag" == *-* ]]; then
  echo "Release check passed: $tag has a suffix, so the version comparison is skipped."
  exit 0
fi

if [[ ! -f "$pyproject" ]]; then
  echo "Release check failed: $pyproject not found." >&2
  exit 1
fi

version="$(python3 -I -c '
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    print(tomllib.load(f).get("project", {}).get("version", ""))
' "$pyproject")" || {
  echo "Release check failed: cannot read $pyproject." >&2
  exit 1
}

if [[ -z "$version" ]]; then
  echo "Release check failed: $pyproject has no [project] version." >&2
  exit 1
fi

if [[ "${tag#v}" != "$version" ]]; then
  echo "Release check failed: tag $tag is version ${tag#v}, but $pyproject says $version. Bump the version first, or tag v$version." >&2
  exit 1
fi

echo "Release check passed: $tag matches $pyproject ($version)."
