# Tomarr

Tomarr does for manga, manhwa and webtoons what Sonarr does for TV: it knows every volume and chapter of a series, watches for new releases, grabs them through your indexers and download client, and files them into your reading library with correct metadata.

## Problem

Self-hosters who read manga and webtoons manage their libraries by hand. The *arr tools they already run for TV, film and music don't understand reading formats, and the ones that do treat a series as a flat list of files. Manga has structure the others ignore:

- Chapters come out weekly, then get collected into volumes months later. A reader often wants chapters now and the volume once it exists.
- The same series is split into volumes differently per edition (Japanese tankōbon, English release, omnibus).
- The best volume data (release dates, synopses, which chapters a volume collects) is in Japanese, from Japanese sources.
- Release names on indexers are inconsistent: volume and chapter ranges, batch packs, scanlation groups, digital versus scan.

## Audience

Self-hosters already running Prowlarr, a download client and Kavita, who read manga, manhwa or webtoons and want the same automation they have for video. Comfortable with Docker and with pasting an API key.

## Core loop

1. The user adds a series. Tomarr resolves the title against MangaBaka and AniList, shows suggestions, and lets the user override the display title and add search aliases.
2. Tomarr builds the series structure: Editions, Volumes and Chapters (or Episodes for webtoons), each volume-to-chapter Mapping tagged with where it came from.
3. Japanese volume data (Rakuten Books, NDL, openBD) is attached to the Japanese Edition. If the user has added a Gemini key, volume synopses are translated, with the original kept alongside.
4. The user picks a Monitor mode, for example chapters until the volume is out, then upgrade to the volume.
5. Tomarr searches Prowlarr for wanted items, limited to indexers with the user's Prowlarr tag and to their configured categories. It parses every release name, scores it against the quality profile, and grabs the best match when the parse is high-confidence. Low-confidence matches wait in Pending review for one-click approval. RSS sync does the same for new releases on a schedule. For webtoons, the platform's RSS feed tells Tomarr when an episode is out.
6. If a wanted Chapter still has no acceptable release after the fallback delay, and the user has connected Suwayomi, Tomarr asks Suwayomi to download that chapter from the source linked to the Series. Prowlarr stays the primary source; Suwayomi only fills gaps.
7. When the download client or Suwayomi finishes, Tomarr imports the files: renames them, converts to CBZ, writes `ComicInfo.xml`, and asks Kavita to scan that folder.

## MVP scope

| In | Detail |
|---|---|
| Formats | Manga, manhwa, webtoons |
| Indexers | Pulled from Prowlarr and filtered by Prowlarr tag, per-indexer categories (default Books/Comics 7030 and Books 7000), plus direct Torznab and Newznab |
| Chapter source | Suwayomi, optional fallback for Chapters indexers don't have. The user runs Suwayomi and chooses its extensions (for example the Keiyoushi extension store) |
| Download clients | qBittorrent, SABnzbd |
| Library server | Kavita (folder scan after import) |
| Metadata | MangaBaka (identity hub), AniList, MangaDex, MangaUpdates, Rakuten Books, NDL, openBD, WEBTOON series RSS |
| LLM | Gemini, bring your own key: synopsis translation, chapter-range extraction from Japanese descriptions, title disambiguation, fallback release parsing |
| Import | Existing-library import, rename templates, CBR to CBZ, `ComicInfo.xml`, hardlinks where possible |
| Review | Interactive search with grab and override for any release; Pending review for low-confidence matches; overrides can be saved as parser test cases or Aliases |
| Other | Quality profiles, monitor modes, wanted list, calendar of upcoming volumes, blocklist, manual import, API key and form login, backups |

## Explicitly out of scope for MVP

- Western comics, light novels and ebooks (ComicVine, Metron and Hardcover come with them). The data model is designed so they fit later.
- Manhua-specific (Chinese) metadata sources.
- Komga and other library servers.
- Tomarr scraping any site itself. Chapter downloads from reader sites only happen through a Suwayomi instance the user runs. WEBTOON is used for metadata and release detection only.
- Installing, configuring or recommending Suwayomi extensions or extension stores. Tomarr ships no source list.
- LLM providers other than Gemini. The provider interface exists; only Gemini is implemented.
- Postgres, multi-user accounts, and a hosted version.
- Native Prowlarr app sync (Prowlarr pushing indexers into Tomarr). See ADR 0002.

## Differentiation

Checked November 2026. Competitors and what they cover:

- **Tankarr**: the closest match. Manga-focused, identifies works through MangaBaka cross-checked with MangaUpdates, AniList, Kitsu and MAL, tracks chapters or volumes, uses *arr-style profiles.
- **Librarr** (JeremiahM37): books, audiobooks and manga in one Go binary, Prowlarr search, imports into Kavita and Komga. Breadth over depth.
- **Kapowarr, Mylar3**: western comics. Mylar3 has native Prowlarr sync.
- **Mnema**: tested before starting Tomarr.

Where Tomarr has to win:

1. **Edition-aware volume and chapter mapping with provenance.** Every mapping says where it came from and can be locked. Omnibus and English splits don't corrupt the Japanese structure.
2. **Japanese-source volume data, translated.** Rakuten Books, NDL and openBD give release dates, upcoming volumes and synopses that English sources lack; Gemini makes them readable.
3. **Webtoons as a first-class format.** Episodes and seasons instead of forced volumes, release detection from official RSS.
4. **Indexers first, Suwayomi for the gaps.** Volumes and well-seeded chapters come from Prowlarr; Chapters that indexers don't carry can still arrive through Suwayomi, under the same monitoring, naming and import rules.

The parser and the mapping data are the moat. The LLM features are the easiest part for a competitor to copy.

## Business model

None for MVP. Open source under AGPL-3.0. AGPL keeps hosted, modified versions open. Contributions come under the DCO and contributors keep their copyright, so dual licensing is not relied on; a CLA is the route if that changes ([ADR 0007](../docs/adr/0007-dco-for-contributions.md)).

## Open questions

- Default port (must not collide with Sonarr 8989, Radarr 7878, Lidarr 8686, Readarr 8787, Prowlarr 9696, Kavita 5000).
- Whether Aladin's Open API is usable for Korean print volumes of manhwa.
- Manhua: treat as manga with English and Japanese metadata only, or leave out of MVP entirely.
- Default fallback delay before a wanted Chapter goes to Suwayomi (for example 24 hours), and whether it's set per Series.
- Which Suwayomi auth modes to support in MVP (none, basic, or the JWT login used in multi-user mode).

## Risks

1. **Chapter availability.** Indexers carry volumes far better than single chapters. Suwayomi fills much of the gap for users who run it; without it, a chapter-first monitor mode may often find nothing. Test against real Prowlarr setups early.
2. **Tankarr overlap.** If Tankarr ships edition handling first, Tomarr's differentiation shrinks to webtoons and Japanese sources.
3. **Third-party API terms and limits.** MangaBaka, Rakuten and Gemini free quotas and terms can change. Every provider is cached and replaceable.
4. **Parser correctness.** A wrong parse can grab the wrong file. Mitigated by Prowlarr tags and categories (fewer irrelevant results), a Confidence threshold (uncertain matches go to Pending review instead of being grabbed), and overrides that become parser test cases. The parser still needs a large, real corpus before the threshold is lowered.
5. **Suwayomi sources.** Most Suwayomi extensions read from unofficial sites. Sources break, change chapter numbering or disappear, and their legal standing varies. Suwayomi is optional and off by default; Tomarr never ships or points to extension stores; chapter numbers from Suwayomi are matched with the same rules as any other source.
