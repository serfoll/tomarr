# Tomarr

Tomarr tracks manga, manhwa and webtoon series down to volumes and chapters, grabs releases through Prowlarr, and imports them into a Kavita library.

## Language

**Series**:
One work as readers know it, independent of language or publisher. Has a Format, a reading direction, external IDs and aliases.
_Avoid_: title, manga, book

**Format**:
What kind of series it is: `manga`, `manhwa`, `webtoon` in MVP; `manhua`, `comic`, `light_novel`, `ebook` later. Decides which units apply (volumes and chapters, or episodes).
_Avoid_: type, category

**Edition**:
One publication of a Series with its own volume numbering: the Japanese tankōbon, an English release, an omnibus, a digital edition. Volumes belong to an Edition, never directly to a Series. One Edition per Series is primary; files are matched against it.
_Avoid_: version, release

**Volume**:
A collected book within an Edition, with a number, title, release date, ISBN, cover and synopsis. Optional: webtoons usually have none.
_Avoid_: tankōbon, book, issue

**Chapter**:
A unit of serialized content within a Series. Numbered with a decimal (`10.5` and `0` are common) and shared across Editions, since editions split the same chapters into different volumes.
_Avoid_: issue, part

**Episode**:
A Chapter on a webtoon platform, kept with the platform's own episode number and an optional season. Mapped to a Chapter number separately, because some platforms reset numbering per season.
_Avoid_: chapter (when talking about the platform's numbering)

**Mapping**:
The record of which Chapters a Volume contains, for one Edition. Every Mapping has a Provenance and can be Locked.
_Avoid_: link, index

**Provenance**:
Where a Mapping or a piece of metadata came from, plus a confidence. In priority order: `user`, `mangadex_aggregate`, `description_parse` (for example `第18話〜第26話収録` from Rakuten or openBD), `llm_extraction`, `inferred`. A higher-priority source never gets overwritten by a lower one.
_Avoid_: source (on its own, it's ambiguous with Provider)

**Locked**:
A Mapping or field the user has fixed by hand. Metadata refreshes never change it.
_Avoid_: pinned, frozen

**Provider**:
An external metadata source behind a common interface: MangaBaka, AniList, MangaDex, MangaUpdates, Rakuten Books, NDL, openBD, WEBTOON.
_Avoid_: source, API, integration

**External ID**:
A Series' or Volume's ID at one Provider. MangaBaka is the identity hub that links IDs across Providers.
_Avoid_: foreign key, remote ID

**Alias**:
Another name for a Series, used both to build search queries and to match Release names. Comes from Providers or from the user.
_Avoid_: alt title, synonym

**Monitor mode**:
What Tomarr looks for in a Series: `chapters_then_volume` (chapters now, upgrade to the volume once released), `volumes_only`, `chapters_only`, `future_only`, `none`.
_Avoid_: tracking, watch

**Wanted**:
A monitored Chapter or Volume with no file, or a file below the quality profile's cutoff.
_Avoid_: missing (Wanted includes upgrades)

**Release**:
One result from an indexer: its raw name, indexer, size, protocol and link. Exists before parsing and is never stored as library content.
_Avoid_: torrent, NZB, download

**Parsed release**:
What the parser extracted from a Release name: series title, Volume and Chapter ranges, group, digital or scan, language, edition hints, file format.
_Avoid_: match, result

**Confidence**:
How sure the parser and matcher are about a Parsed release: `high`, `medium` or `low`, from how exactly the title matched an Alias and how cleanly the Volume and Chapter ranges parsed. Only releases at or above the threshold are grabbed automatically.
_Avoid_: score (Score is the quality-profile ranking, a separate number)

**Pending review**:
Accepted releases below the Confidence threshold, held for the user to approve or reject instead of being grabbed. Approving can save the release name as a parser test case or add an Alias.
_Avoid_: queue (that's the download client's), manual

**Decision**:
Whether a Parsed release is accepted or rejected for a Series, with a score and the reasons. Every rejection has a reason the user can read.
_Avoid_: filter result

**Indexer tag**:
A Prowlarr tag that marks which indexers Tomarr uses. Tomarr only pulls indexers carrying the tag set in its settings.
_Avoid_: label, filter

**Category**:
A Newznab or Torznab category ID that limits what an indexer search returns. Defaults to Books/Comics (7030) and Books (7000); set per indexer.
_Avoid_: section, type

**Chapter source**:
A service that downloads single Chapters directly rather than through an indexer. Suwayomi is the only one in MVP. Used only as a fallback after Prowlarr.
_Avoid_: scraper, reader site, indexer

**Source link**:
The connection between a Tomarr Series and one manga entry on one Suwayomi source (source ID plus manga ID), chosen or confirmed by the user. A Series has at most one active Source link.
_Avoid_: mapping (that word is for volumes and chapters)

**Fallback delay**:
How long a wanted Chapter waits for an acceptable Prowlarr release before Tomarr asks the Chapter source for it.
_Avoid_: timeout, grace period

**Grab**:
Sending an accepted Release to a download client, or asking a Chapter source to download a Chapter.
_Avoid_: download (that's the client's job)

**Import**:
Taking a finished download into the library: rename, convert to CBZ, write `ComicInfo.xml`, link or move into the Series folder, notify Kavita.
_Avoid_: process, sync

**Upgrade**:
An Import that replaces existing files, for example a full Volume replacing loose Chapters, or digital replacing scan.
_Avoid_: replace

**Quality profile**:
The ranked preferences used to score Parsed releases: digital over scan, file format order, languages, preferred groups, cutoff.
_Avoid_: settings, filter

**Command**:
A unit of background work stored in the database and run by the command queue: refresh metadata, search, RSS sync, import, translate. Visible in the UI with its status.
_Avoid_: job, task (in code), worker

**Library server**:
The reading app that serves the files: Kavita in MVP, Komga later.
_Avoid_: reader, media server

**Translation**:
A machine-translated text (usually a Volume synopsis) stored next to its original, with the model and time. Can be edited and Locked.
_Avoid_: localization

## Secrets and logs

Users paste API keys and passwords for Prowlarr, download clients, Suwayomi, Kavita, Rakuten and Gemini. These keys never appear in logs, error reports, API responses or the UI after saving (the UI shows them masked). Log lines carry IDs and Command names, never full request URLs with query strings, because several Providers put keys in the query string.
