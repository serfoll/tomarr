# 0007: Developer Certificate of Origin for contributions

Status: accepted, November 2026

## Context

Tomarr is licensed AGPL-3.0 and has one copyright holder. There is no business model for the MVP, and no one outside the project has sent a contribution yet. Nothing in the repository says what a contributor promises when they send code, and nothing checks it. The decision has to land before the first outside pull request.

The two usual options differ in what the maintainer gets. A Developer Certificate of Origin (DCO) is a statement each contributor makes per commit: they wrote the code or have the right to submit it under the project's license. They keep their copyright. A Contributor License Agreement (CLA) grants the maintainer extra rights, including the right to relicense, and needs a legal text, a place to store signatures and a signing step for every new contributor.

## Decision

- Contributions are accepted under the Developer Certificate of Origin 1.1. Every commit carries a `Signed-off-by` line, which `git commit -s` adds.
- A workflow in this repository checks the sign-off on pull requests. It uses no third-party app and no third-party action.
- Pull requests authored by the repository owner are exempt. The workflow decides this from the author login in the pull request event, never from a commit email, which anyone can set.
- `CONTRIBUTING.md` states the policy and quotes the DCO text verbatim.

## Consequences

- Contributors keep the copyright on what they send. The maintainer cannot relicense or dual-license contributed code without each contributor's consent, so `CONTEXT/PRODUCT.md` no longer relies on dual licensing.
- A CLA can be introduced later. It would cover only contributions made after it starts. Code accepted under the DCO before then stays under the DCO.
- The check fails a pull request without a sign-off, but it only blocks a merge once a ruleset on `main` requires it. The ruleset is set up after the workflow is merged.
- The exemption means the owner's pull requests are not certified, whoever wrote the commits in them. That is acceptable because the owner is the copyright holder.
- A bot pull request, such as one from Dependabot or Renovate, would fail until the check exempts it. That is decided when one is added.
- A contributor can lie in a sign-off, and a pull request can edit the workflow that checks it. The check catches honest mistakes. The maintainer's review before merge is the real gate.
