#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
script="$here/check-dco.sh"

failures=0
out=""
code=0

# commit <sha> <author-email> <message> <parent-count>
commit() {
  jq -nc --arg sha "$1" --arg email "$2" --arg msg "$3" --argjson parents "$4" \
    '{sha: $sha, parents: [range($parents) | {sha: "p\(.)"}],
      commit: {message: $msg, author: {email: $email}}}'
}

# run <stdin> <author-login> <exempt-login>
run() {
  code=0
  out="$(printf '%s' "$1" | bash "$script" "$2" "$3" 2>&1)" || code=$?
}

fail() {
  echo "FAIL: $1"
  echo "  $2"
  echo "  exit code: $code"
  echo "  output: $out"
  failures=$((failures + 1))
}

expect_exit() {
  [[ "$code" -eq "$2" ]] || fail "$1" "expected exit $2"
}

expect_out() {
  [[ "$out" == *"$2"* ]] || fail "$1" "expected output to contain: $2"
}

expect_no_out() {
  [[ "$out" != *"$2"* ]] || fail "$1" "expected output not to contain: $2"
}

me="dev@example.com"
sign="Signed-off-by: Dev Eloper <$me>"

run "$(commit aaaaaaa1111111 "$me" "Add thing

$sign" 1)" alice owner
expect_exit "a: signed commit with matching email passes" 0

run "$(commit bbbbbbb2222222 "$me" "Add other thing" 1)" alice owner
expect_exit "b: unsigned commit fails" 1
expect_out "b: names the 7-character SHA" "bbbbbbb"
expect_no_out "b: SHA is cut to 7 characters" "bbbbbbb2"
expect_out "b: names the subject" "Add other thing"

run "$(commit ccccccc3333333 "$me" "Add thing

Signed-off-by: Dev Eloper <someone-else@example.com>" 1)" alice owner
expect_exit "c: sign-off with a different email fails" 1
expect_out "c: names the SHA" "ccccccc"

run "$(commit ddddddd4444444 "Dev@Example.com" "Add thing

$sign" 1)" alice owner
expect_exit "d: email differing only by case passes" 0

run "$(commit eeeeeee5555555 "$me" "Merge branch 'main' into feature" 2)" alice owner
expect_exit "e: merge commit without sign-off is skipped" 0

run "$(commit fffffff6666666 "$me" "Add thing

First paragraph of the body.
$sign
Last paragraph of the body." 1)" alice owner
expect_exit "f: sign-off in the middle of the body passes" 0

run "$(commit 1111111aaaaaaa "$me" "Add thing

  $sign" 1)" alice owner
expect_exit "g: indented sign-off fails" 1

run "$(commit 2222222bbbbbbb "$me" "Add thing

I forgot to add $sign to this." 1)" alice owner
expect_exit "g: sign-off inside a sentence fails" 1

run "$(commit 3333333ccccccc "$me" $'Add thing\r\n\r\n'"$sign"$'\r\n' 1)" alice owner
expect_exit "h: CRLF line endings with a valid sign-off pass" 0

run "$(
  commit 4444444aaaaaaa "$me" "First

$sign" 1
  commit 5555555bbbbbbb "$me" "Second" 1
  commit 6666666ccccccc "$me" "Third

$sign" 1
)" alice owner
expect_exit "i: three commits, one bad, fails" 1
expect_out "i: names the bad SHA" "5555555"
expect_no_out "i: does not name the first good SHA" "4444444"
expect_no_out "i: does not name the last good SHA" "6666666"

unsigned="$(commit 7777777aaaaaaa "$me" "Unsigned" 1)"

run "$unsigned" owner owner
expect_exit "j: PR author equal to the exempt login passes" 0
expect_out "j: prints the owner line" "repository owner"

run "$unsigned" alice owner
expect_exit "k: PR author different from the exempt login fails" 1

run "" alice owner
expect_exit "l: empty stdin is unusable input" 2

run "$(commit 8888888aaaaaaa "$me" "Add thing

$sign
Signed-off-by: Co Signer <cosigner@example.com>" 1)" alice owner
expect_exit "m: a second co-signer line still passes" 0

run "$unsigned" "" ""
expect_exit "n: an empty exempt login never exempts an empty author" 1

run "$unsigned" alice ""
expect_exit "n: an empty exempt login never exempts anyone" 1

run "not json" alice owner
expect_exit "extra: input that is not JSON is unusable" 2

# The workflow runs the script behind `gh api ... |` under pipefail, so an owner PR that
# exits without draining stdin would turn the producer's SIGPIPE (141) into a red check.
pipe_statuses() {
  (
    set +e
    set -o pipefail
    "$@" | bash "$script" owner owner >/dev/null 2>&1
    echo "${PIPESTATUS[*]}"
  )
}

slow_producer() { sleep 0.2; printf '%s\n' "$unsigned"; }
large_producer() { for _ in $(seq 3000); do printf '%s\n' "$unsigned"; done; }

code=0
out="$(pipe_statuses slow_producer)"
[[ "$out" == "0 0" ]] || fail "o: owner PR behind a slow producer under pipefail" "expected pipe statuses '0 0'"
out="$(pipe_statuses large_producer)"
[[ "$out" == "0 0" ]] || fail "o: owner PR behind a large producer under pipefail" "expected pipe statuses '0 0'"

many() { for _ in $(seq "$1"); do printf '%s\n' "$2"; done; }
signed_one="$(commit 9999999aaaaaaa "$me" "Add thing

$sign" 1)"

run "$(many 250 "$signed_one")" alice owner
expect_exit "p: 250 commits cannot be fully listed and are unusable" 2
expect_out "p: says GitHub lists at most 250 commits" "at most 250"

run "$(many 249 "$signed_one")" alice owner
expect_exit "p: 249 signed commits still pass" 0

run "$(many 250 "$signed_one")" owner owner
expect_exit "p: an owner PR with 250 commits is still exempt" 0

run "$(commit 0000000aaaaaaa "$me" "" 1)" alice owner
expect_exit "q: empty commit message fails" 1
expect_no_out "q: empty subject is not printed as null" "null"

if [[ "$failures" -gt 0 ]]; then
  echo "$failures assertion(s) failed"
  exit 1
fi
echo "all cases passed"
