# Tomarr

Tomarr is a self-hosted *arr for manga, manhwa and webtoons. It tracks each series down to its volumes and chapters, finds releases through Prowlarr, sends them to your download client, imports them with clean metadata and tells Kavita to rescan. Suwayomi can optionally fill in single chapters that indexers don't have.

Early development. Not usable yet.

## Project docs

- `CONTEXT/` has the product scope, glossary, architecture and the rules for working in this repo. Start with `CONTEXT/PRODUCT.md`.
- `docs/adr/` has the architecture decision records.
- Contributions are welcome under the DCO. See `CONTRIBUTING.md`.

## Reset a lost password

1. Set `TOMARR__AUTH__RESET_PASSWORD=true` and restart Tomarr.
2. Open Tomarr and sign up again with a new username and password.
3. Remove `TOMARR__AUTH__RESET_PASSWORD` and restart Tomarr.

The sign-up page opens once each time the variable is set. A restart with the variable still set does not reopen it. Browsers signed in before the reset have to sign in again with the new password.

## License

AGPL-3.0. See `LICENSE`.
