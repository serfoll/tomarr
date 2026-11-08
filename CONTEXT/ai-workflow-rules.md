# AI workflow rules

Rules for how an agent behaves while writing code in this repo. They live here so they apply no matter which agent or machine does the work.

## No tech assumptions

Check what's decided before reaching for something else. The stack is in `CLAUDE.md` and `docs/adr/`. Don't swap in a different framework, ORM, queue, database or LLM SDK because it's more familiar. If a decided choice doesn't fit a new requirement, say so and ask.

## No invented solutions

Don't invent API endpoints, response fields, SDK methods or config keys for external services. Confirm against the provider's documentation, a recorded cassette, or by asking. This matters most for MangaBaka, Rakuten Books, NDL, openBD, Prowlarr, Suwayomi's GraphQL schema, Kavita and the Gemini SDK, where a guessed field name fails silently.

## No hallucination

Function names, file paths, settings, environment variables: if it wasn't read from the codebase or a verified doc, it doesn't exist. Search before referencing.

## Keep it simple (KISS)

Pick the simplest solution that solves the problem in front of you.

## Don't over-simplify

Simple isn't incomplete. A parser that drops release names it can't handle instead of returning a reason is a bug, not a simplification.

## You aren't gonna need it (YAGNI)

Don't build for requirements that haven't arrived. Comics, light novels, ebooks, Komga, Postgres, multi-user accounts and LLM providers other than Gemini are out of scope in `CONTEXT/PRODUCT.md`. Keep the data model open to them; don't scaffold them.

## Don't repeat yourself (DRY)

Extract on the second use, not before.

## SOLID

- One job per function, class or module.
- New Providers, download clients and library servers are added by implementing the interface, not by editing callers.
- Any implementation of an interface works wherever the interface is accepted.
- Don't force an adapter to implement methods it can't support; split the interface instead.
- Depend on interfaces, not concrete adapters.

## Separation of concerns

Routes validate and delegate. Services decide. Adapters translate. The parser is pure. Don't mix them.

## No AI-slop

No inflated vocabulary, no em dashes, no rule-of-three padding, no inline-header bullet lists, no sycophantic tone, in code comments, commit messages or PR descriptions. Full rules in `CONTEXT/copy.md`.

## Lint before calling it done

Run the backend lint, type and test commands and `pnpm lint` before considering a change finished. A change that fails them is in progress, not done.

## Testing

Tasks picked up through `/start-task` and `/build-task` write their tests as part of that TDD workflow (failing test first, then the implementation). Follow it for any task that goes through those skills.

## Never hit live services from tests

Record a cassette once against the real API with your own key, filter secrets out, commit it, and replay it. Never leave a test that calls a live API, and never commit a cassette containing a key.

## Humanize before it ships

Run commit messages, PR descriptions and any other user-facing text through `/humanizer` before finalizing.

## Dependencies need sign-off

Don't add a package to `pyproject.toml` or `package.json` without asking first. The "Approved dependencies" section of `CLAUDE.md` is the list of record.

## Ask, don't assume

If a requirement, a design decision or a piece of scope is unclear, ask. A wrong guess costs more than a short question.

## Maintainable by people and agents

This code is read and edited by the user and by AI agents, often without much context each time. Clear names, small files, no cleverness that only makes sense if you were there when it was written.
