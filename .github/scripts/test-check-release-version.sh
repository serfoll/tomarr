#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/check-release-version.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

failures=0
err=""
code=0

fail() {
  echo "FAIL: $1"
  echo "  $2"
  echo "  exit code: $code"
  echo "  stderr: $err"
  failures=$((failures + 1))
}

# run <script args...>
run() {
  code=0
  err="$(bash "$script" "$@" 2>&1 >/dev/null)" || code=$?
}

expect_exit() {
  [[ "$code" -eq "$2" ]] || fail "$1" "expected exit $2"
}

expect_err() {
  [[ "$err" == *"$2"* ]] || fail "$1" "expected stderr to contain: $2"
}

pyproject="$work/pyproject.toml"
printf '[project]\nname = "tomarr"\nversion = "0.1.0"\n' >"$pyproject"

run v0.1.0 "$pyproject"
expect_exit "a: tag matching the pyproject version passes" 0

run v0.1.1 "$pyproject"
expect_exit "b: stable tag differing from the pyproject version fails" 1
expect_err "b: names the tag version" "0.1.1"
expect_err "b: names the pyproject version" "0.1.0"

run v0.0.0-ci.1 "$pyproject"
expect_exit "c: pre-release tag skips the version comparison" 0

run v1.2.3-rc.1 "$pyproject"
expect_exit "c: release candidate tag skips the version comparison" 0

for bad in 0.1.0 vfoo v1.2 v01.2.3 v1.02.3 v1.2.03 v1.2.3+build v1.2.3- v1.2.3-rc..1 v1.2.3-rc.; do
  run "$bad" "$pyproject"
  expect_exit "d: bad format '$bad' fails" 1
  expect_err "d: bad format '$bad' says the format is wrong" "not a valid release tag"
done

run "" "$pyproject"
expect_exit "d: empty tag fails" 1
expect_err "d: empty tag says the format is wrong" "not a valid release tag"

run
expect_exit "d: no argument is a usage error" 2
expect_err "d: no argument prints usage" "usage:"

# A pre-release tag with a wrong format must still fail the format check.
run v1.2.3-rc..1 "$work/missing.toml"
expect_exit "e: format is checked before the file is read" 1
expect_err "e: names the format problem" "not a valid release tag"

printf '[project]\nname = "tomarr"\n' >"$work/no-version.toml"
run v0.1.0 "$work/no-version.toml"
expect_exit "f: pyproject without a version fails" 1
expect_err "f: says the version is missing" "no [project] version"

printf '[tool.other]\nversion = "0.1.0"\n' >"$work/no-project.toml"
run v0.1.0 "$work/no-project.toml"
expect_exit "f: version outside [project] does not count" 1
expect_err "f: says the version is missing" "no [project] version"

run v0.1.0 "$work/missing.toml"
expect_exit "g: missing pyproject fails" 1
expect_err "g: names the missing file" "missing.toml"

printf 'this is = not [valid toml\n' >"$work/broken.toml"
run v0.1.0 "$work/broken.toml"
expect_exit "h: unparseable pyproject fails" 1
expect_err "h: says the file cannot be read" "cannot read"

if [[ "$failures" -gt 0 ]]; then
  echo "$failures assertion(s) failed"
  exit 1
fi
echo "all cases passed"
