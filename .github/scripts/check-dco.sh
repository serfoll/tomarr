#!/usr/bin/env bash
# Usage: check-dco.sh <pr-author-login> <exempt-login>
# Reads GitHub API commit objects on stdin, one JSON object per commit.
# Exit 0: every commit is signed off (or the author is exempt). Exit 1: a commit is missing
# a sign-off. Exit 2: unusable input.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: check-dco.sh <pr-author-login> <exempt-login>" >&2
  exit 2
fi

pr_author="$1"
exempt="$2"

if [[ -n "$exempt" && "$pr_author" == "$exempt" ]]; then
  # Drain stdin so the producer is not killed by SIGPIPE, which fails the step under pipefail.
  cat >/dev/null
  echo "DCO check skipped: the PR author is the repository owner."
  exit 0
fi

# A merge commit has two parents and carries no sign-off of its own. A sign-off counts only
# as a whole line, so `Signed-off-by` inside a sentence or indented does not match.
# shellcheck disable=SC2016 # jq program, not shell: $author and $checked are jq variables
filter='
  def signed_off:
    (.commit.author.email | ascii_downcase) as $author
    | .commit.message
    | gsub("\r"; "")
    | split("\n")
    | any(.[]; [capture("^Signed-off-by: .+ <(?<email>[^<>]+)>[ \t]*$")]
                | any(.email | ascii_downcase == $author));
  . as $all
  | [.[] | select((.parents | length) < 2)] as $checked
  | {
      total: ($all | length),
      checked: ($checked | length),
      failed: [
        $checked[] | select(signed_off | not)
        | {sha: .sha[0:7], subject: (.commit.message | gsub("\r"; "") | split("\n")[0] // "")}
      ]
    }
'

result="$(jq -s "$filter" 2>/dev/null)" || {
  echo "DCO check failed: stdin is not a stream of GitHub commit objects." >&2
  exit 2
}

if [[ "$(jq '.total' <<<"$result")" -eq 0 ]]; then
  echo "DCO check failed: no commits were passed in." >&2
  exit 2
fi

# GitHub lists at most 250 commits per PR, so a count of 250 may be a truncated list.
if [[ "$(jq '.total' <<<"$result")" -ge 250 ]]; then
  echo "DCO check failed: GitHub lists at most 250 commits per PR, so this PR cannot be fully checked." >&2
  exit 2
fi

checked="$(jq '.checked' <<<"$result")"
failed="$(jq '.failed | length' <<<"$result")"

if [[ "$failed" -eq 0 ]]; then
  echo "DCO check passed: $checked commit(s) checked, all signed off."
  exit 0
fi

echo "DCO check failed: $failed of $checked commit(s) have no matching Signed-off-by line."
echo
jq -r '.failed[] | "  \(.sha) \(.subject)"' <<<"$result"
cat <<'MSG'

A sign-off is a line "Signed-off-by: Your Name <you@example.com>" in the commit message.
The email must match the commit author email. To fix:

  Last commit only:   git commit --amend -s
  Several commits:    git rebase --signoff HEAD~N
                      (N is the number of commits in the pull request; its page shows the count)

Then force-push the branch (git push --force-with-lease).
MSG
exit 1
