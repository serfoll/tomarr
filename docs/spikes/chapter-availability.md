# Spike: chapter availability on real Prowlarr indexers

Run on 2026-11-08 for issue #1. Risk 1 in `CONTEXT/PRODUCT.md` says indexers carry volumes far better than single chapters. This measures how true that is on one real setup, before Monitor modes and the Fallback delay are built around it.

## Result in short

- Single chapters turned up for 2 of the 18 series: One Piece and Dandadan, the two biggest ongoing titles. Nothing for the other three ongoing manga, the manhwa or the webtoons.
- Volumes or complete-series packs turned up for 15 of the 18 series through Prowlarr, and 16 once MyAnonamouse is searched directly. Tower of God and unOrdinary have nothing.
- 1337x had a DNS resolver problem on the first pass and returned nothing, so all 44 of its searches were repeated after the fix. It works, but it carries almost no manga.
- Webtoons and most manhwa are close to absent from torrent indexers. The category filter is not the cause. The unfiltered searches added anime and ebooks, not more manga.
- Recommendation: default Monitor mode `volumes_only`, with or without Suwayomi. Torrent volumes are the better source for scan and translation quality, so chapters stay an explicit opt-in per series. The Fallback delay should vary per series and count from the chapter's release timestamp (MangaDex or MangaUpdates). No source checked publishes a future chapter date. A flat 24 hours is only the starting value.

## Method

- Prowlarr 2.7.0.5723 on a separate box. Queries went through `GET /api/v1/search` with `query`, `type=search`, `categories` and `indexerIds`, authenticated by the `X-Api-Key` header. The parameter names were confirmed against live responses because the instance's Swagger page sits behind the UI login.
- Indexers: every enabled indexer with a Books category and no tag filter. Five qualified: 1337x, Knaben, MyAnonamouse, Nyaa.si and RetroToon. SeedCore and sukebei.nyaa.si expose no Books category and were left out. All five are torrent indexers. Three are public (1337x, Knaben, Nyaa.si) and two are private (MyAnonamouse, RetroToon).
- Categories exposed under Books: 1337x, Knaben and MyAnonamouse expose 7000 plus Comics (7030). RetroToon exposes 7000 and 7030. Nyaa.si exposes only 7000.
- Each series was searched twice per title, once with categories 7000 and 7030 and once with no category filter. Series with a common alternate title were searched under both names. 44 searches in total, one at a time with a 5 second pause. 1337x failed to resolve during the first pass, so its searches were repeated afterwards and are counted from the rerun. No 429s or HTTP errors came back.
- A result counts as relevant if its name contains the series title (or a known alternate title). Relevant names were classified by rule as chapter, volume, pack (a range of volumes or chapters, or a "complete" release), series (a whole-run release with no number, such as `Solo Leveling (2021-2026) (Digital)`), video, novel or extra, or other. The rules are regexes and were adjusted by reading samples, so treat the counts as approximate.
- The table counts only the category-filtered searches, which is what Tomarr would do by default. Counts are release names, not distinct chapters or volumes.

## Per series (category-filtered searches)

| Series | Group | Chapter | Volume | Pack or series | Notes |
|---|---|---:|---:|---:|---|
| One Piece | ongoing manga | 25 | 108 | 51 | Chapters 1190 to 1197 present, 1180 to 1189 missing |
| Dandadan | ongoing manga | 40 | 16 | 6 | Chapters 240 to 251 all present |
| Kagurabachi | ongoing manga | 0 | 2 | 5 | |
| Blue Box | ongoing manga | 0 | 3 | 3 | |
| Witch Hat Atelier | ongoing manga | 0 | 5 | 6 | |
| Fullmetal Alchemist | finished manga | 1 | 2 | 16 | The one chapter is an old single upload |
| Jujutsu Kaisen | finished manga | 0 | 9 | 11 | Two whole-run uploads from 1337x |
| Demon Slayer | finished manga | 0 | 8 | 15 | 25 English novels by another author filtered out as noise |
| Monster | finished manga | 0 | 0 | 6 | |
| Solo Leveling | manhwa | 1 | 3 | 16 | 31 novel and extra hits filtered out |
| Tower of God | manhwa | 2 | 0 | 0 | The two chapters (210 and 214) are about 12 years old. Everything else was novels |
| The Beginning After the End | manhwa | 0 | 2 | 4 | |
| Omniscient Reader's Viewpoint | manhwa | 0 | 4 | 11 | |
| unOrdinary | webtoon | 0 | 0 | 0 | No relevant results at all |
| True Beauty | webtoon | 0 | 0 | 1 | |
| Lore Olympus | webtoon | 0 | 0 | 0 | Two ebook hits, no comics |
| Orb: On the Movements of the Earth | control | 0 | 0 | 4 | |
| Look Back | control | 0 | 0 | 1 | One-shot, so a single release is the whole result |

Total across the 18 series: 69 chapter names, 162 volume names, 156 pack or series names. The unfiltered searches added 90 more manga-like names (Knaben 51, MyAnonamouse 23, Nyaa.si 12, RetroToon 4), mostly full-series or volume releases filed outside the Books categories. They also pulled in about 1,800 anime video releases, which the category filter correctly hides.

## Per indexer (category-filtered searches)

| Indexer | Chapter | Volume | Pack or series | Comment |
|---|---:|---:|---:|---|
| Knaben | 32 | 31 | 95 | Aggregates other trackers, so many names duplicate Nyaa.si |
| MyAnonamouse | 2 | 126 | 36 | Mostly volumes, in English, German, Russian and other languages. Also returns many unrelated novels. A direct search finds more than three times as many volumes (see Direct MyAnonamouse check) |
| Nyaa.si | 33 | 5 | 23 | Where nearly all single chapters come from |
| RetroToon | 0 | 0 | 0 | Nothing under the Books categories. The unfiltered search added 4 manga-like names, plus anime video |
| 1337x | 2 | 0 | 2 | Almost no manga. The 2 chapters are the old Tower of God files and the 2 packs are Jujutsu Kaisen. Other title matches were game repacks, anime, adult image sets and unrelated ebooks |

## Chapter timing

Only One Piece and Dandadan have enough chapters to look at timing. Publish dates of the newest copy of each chapter:

- Dandadan chapters 246 to 251 were indexed about 7 days apart, on a steady weekly pattern. Chapter 251 appeared 5 days before the search.
- One Piece chapters 1192 to 1197 were indexed 5 to 15 days apart. Chapters 1180 to 1189 never showed up in any indexer. Knaben and Nyaa.si never hit the 100 result cap, so this gap is real.

This is a single snapshot. It shows when a torrent was published, not when the chapter was released officially, so it cannot say how long the wait is. It only shows that, when a chapter torrent exists, it arrives on the weekly schedule, and that for most series none exists.

## Chapter release dates

The Fallback delay needs a date to count from. Sources checked on 2026-11-08, from their own APIs or docs:

| Source | What it gives for a chapter | Future dates? |
|---|---|---|
| MangaDex feed (`/manga/{id}/feed`, public, no key) | `publishAt`, `readableAt`, `translatedLanguage`, and `externalUrl` for official chapters hosted elsewhere (MANGA Plus) | No. A chapter appears when it is released |
| MangaUpdates (`POST /v1/releases/search`, public) | `release_date` (day only), chapter, volume, the releasing group (for Dandadan, "Viz+MANGA Plus"), and `time_added` | No, same as above |
| Suwayomi GraphQL `ChapterType` | `uploadDate`, `fetchedAt`, `scanlator` (nullable), `chapterNumber`, all read from the Suwayomi-Server source on GitHub | No. The date is what the extension reports once it lists the chapter. Not tested against a running server |
| AniList | Nothing per chapter. `nextAiringEpisode` and `airingSchedule` are documented for anime, and `chapters` is the total when complete | No |

None of them publishes when the next chapter is due. What they do give is an exact release time for a chapter that just came out. Tomarr can poll MangaDex or MangaUpdates for a followed series, notice a new chapter, and start the delay from that timestamp instead of from "now". MangaDex and MangaUpdates agreed on every Dandadan date except chapter 242 (2026-07-27 on MangaUpdates, 2026-07-29 on MangaDex), where MangaDex was two days late. MangaUpdates matched the torrent in that case.

The next release can only be guessed from cadence. Dandadan is weekly on Mondays with skipped weeks (chapters 246 and 247 came 21 days apart), so cadence is a hint and not a schedule.

How long torrents lag behind these dates, measured against MangaDex release times:

- **Dandadan:** Nyaa.si torrents appeared between 1.6 hours before and 1.5 hours after the MangaDex release for 8 of 9 chapters checked. Knaben, which mirrors Nyaa.si, was 0.4 to 4.5 hours after. The exception is chapter 242, a torrent 48 hours before MangaDex, which matches the MangaUpdates date.
- **One Piece:** the earliest torrent for each of chapters 1191 to 1197 appeared 3.6 to 48.6 hours before the English release on MangaDex, and for most of them 40 to 49 hours before. Their names look like Japanese raws (one reads `One Piece 1197 [JP]`). The `(Digital)` copy of chapter 1190 appeared 56 hours after the English release.

So the first torrent for a chapter is not always the one a reader wants. Which language and edition a torrent is, and which one the user wants, decides how long to wait. This is a point for the parser (#19) and the Decision engine (#37), not only for the delay.

## Direct MyAnonamouse check

Prowlarr's MyAnonamouse results were capped at 100 per query and came from an account setup without VIP content. To see what they hid, the same 18 series were searched directly through MyAnonamouse's own JSON search (`/tor/js/loadSearchJSONbasic.php`, which needs a logged-in session), with the text matched against title, series and author and results paged past the cap.

- All manga sits in one category, 61 "Ebooks - Comics/Graphic novels". Other categories returned fantasy novels, audiobooks and art books.
- The direct search found 386 volume names, 47 pack or whole-run names and no single chapters, against 126 volumes, 36 packs and 2 chapters through Prowlarr. The 23 "chapters" a first pass flagged were German volumes numbered like `Solo Leveling 13`, volume ranges and English webtoon chapter ranges such as `Solo Leveling #000-116`.
- 225 of the 386 volumes are flagged VIP. Without them the direct search still finds 161 volumes against Prowlarr's 126, so the result cap and relevance trimming hid some as well. Whether the account used here can download VIP-flagged releases was not tested.
- By language the volumes are 212 English, 141 German, 18 Russian, 8 French, 5 Italian and 2 Portuguese. Counting only English volumes that are not VIP-flagged leaves 137, 97 of them One Piece.
- Series with something new: Lore Olympus gains two pack names, so 16 of the 18 series now have a volume or pack somewhere. Tower of God and unOrdinary still have none.
- MyAnonamouse is not a webtoon source. Of the 7 manhwa and webtoon series, 5 returned nothing (Tower of God, The Beginning After the End, Omniscient Reader's Viewpoint, unOrdinary, True Beauty). The only hits were Solo Leveling and Lore Olympus, both of which exist as print books, plus three English chapter-range packs for Solo Leveling. Webtoons will need other sources: Suwayomi as the chapter source (ADR 0006) and the WEBTOON RSS feed as the release signal (`CONTEXT/PRODUCT.md`).
- The result does not change the recommendation. MyAnonamouse has no single chapters, and its volumes are what the default Monitor mode relies on.

The direct names are not in the fixtures. They carry no `by Author [ENG / CBZ]` suffix, so they differ from what the parser will see coming through Prowlarr. Whether Tomarr should ever call MyAnonamouse directly instead of through Prowlarr is a separate decision, and ADR 0002 currently says to pull indexers from Prowlarr.

### Getting Prowlarr close to the direct result

Two things made Prowlarr's MyAnonamouse view smaller than the direct one. One is set per request and one is set on the indexer in Prowlarr.

Per request, which Tomarr controls:

- `GET /api/v1/search` accepts `limit` and `offset` (confirmed on this instance, not found in the Swagger page, which sits behind the login). The default of 100 is not a hard limit. `limit=300` returned 300 distinct results and `offset=100` returned a new page with no overlap.
- Sending only the Comics category (7030) to MyAnonamouse cut One Piece from 1,000 results to 333 and removed the novels.
- With `limit=1000` and `categories=7030`, relevant non-VIP results matched the direct search almost exactly: One Piece 98 volumes and 14 packs against 99 and 14, Jujutsu Kaisen 8 and 1 against 8 and 1, Blue Box 3 and 0 against 3 and 0, Dandadan 17 and 3 against 17 and 3. Solo Leveling did not match (4 volumes against 19), and the cause was not found.

On the indexer in Prowlarr, which the user controls and a request cannot change:

- The indexer's Search Type is set to "Not VIP". Setting it to "All torrents" is what would bring in the 225 VIP-flagged volumes. Whether the account can then download them was not tested, and the setting was not changed.
- Search in description, series and filenames are all on. The direct search matched title, series and author only. Turning off description and filenames is the likely way to cut noise, but this was not tested.

Prowlarr pages upstream when `limit` is large, so a big limit probably costs several requests to the tracker per search. How many was not measured, and it matters for trackers with query limits.

## Caveats

- One setup, five indexers. A user with different indexers, especially private trackers with strong manga coverage, may see more chapters.
- Through Prowlarr, MyAnonamouse hit its 100 result cap on 6 of the series (Blue Box, Demon Slayer, One Piece, The Beginning After the End, Tower of God, True Beauty), and the account has no VIP content, sources or uploads enabled. A direct search showed that this hid a lot: 386 volumes against 126, 225 of them VIP-flagged. The Per series and Per indexer tables still show the Prowlarr view, which is what Tomarr would see with the same setup.
- Series status (ongoing or finished) is from memory, not checked against a provider.
- The classifier is regex based. About 3% of relevant names (14 of roughly 480) stayed unclassified. Language editions are counted together with English ones.

## Recommendation

**Default Monitor mode.** `volumes_only`, whether or not Suwayomi is connected. Chapters were findable for 2 of 18 series, so a chapter-first default would leave 16 of them with nothing to grab until the volume came out. Linking Suwayomi should not change the default either. Torrent volumes usually come with better scans and translation than a chapter source, so Tomarr should prefer them and treat chapters as a deliberate choice. `chapters_then_volume` stays available per series for people who want chapters now and accept lower quality until the volume replaces them (ADR 0006).

**Fallback delay.** Start at 24 hours, the example already in `CONTEXT/PRODUCT.md`, but do not treat it as a single global truth. When a chapter appears on an indexer depends on when an uploader decides to post it. Two series were measured (see Chapter release dates). Dandadan torrents land within about 4 hours of the release, so 24 hours is generous there. For One Piece the torrent a reader wants can arrive 2 or more days after the English release, so a flat 24 hours would send chapters to Suwayomi that an indexer would have supplied. That is why the value should vary per series. Three points follow:

- Where a steady chapter uploader exists (Dandadan) the torrent follows the release within hours. Where it does not (One Piece), the wait depends on which edition the user accepts.
- For series with no chapter torrent in the history at all (3 of the 5 ongoing manga here), waiting is pointless. A per-series rule that skips the delay when Prowlarr has never returned a chapter for that series is worth considering when #52 is built.
- Anchor the delay to the chapter's release timestamp from MangaDex or MangaUpdates (see Chapter release dates), so the wait counts from when the chapter came out. No source checked publishes the next chapter's date, so "next release" can only be estimated from cadence. `CONTEXT/PRODUCT.md` says Rakuten Books, NDL and openBD give upcoming volume dates, which covers the volume side. These sources need verifying again when the adapters are built (#21 to #29).

To replace the 24 hour guess with a measured value, have `RssSync` (#41) log the first time Tomarr sees each chapter and compare it with the expected release date, where one is known. A few weeks of that data gives a real lag distribution per series.

## Raw release names

`backend/tests/fixtures/releases/raw/` holds one `.txt` per series (17 files, 2,083 names, no URL, magnet link or key). A name is kept if it contains the series title or a known alternate title, so the files include the video and novel names the parser will also have to reject. unOrdinary has no file because nothing relevant came back. From 1337x only results filed under the Books categories are kept, because its unfiltered results are mostly game repacks and adult image sets that share a title word. The parser corpus work (#19) starts from these.
