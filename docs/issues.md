# Tomarr MVP issues


## M0 Scaffolding

1. **Spike: measure manga chapter availability on real Prowlarr indexers** (type:spike, area:search)
2. **Scaffold repo layout, license and docs** (type:scaffold, area:infra)
3. **Sign off the initial dependency list** (type:scaffold, area:infra)
4. **Contribution policy: DCO or CLA** (type:scaffold, area:infra)
5. **Scaffold backend: uv, FastAPI app factory, ruff, pyright, pytest** (type:scaffold, area:backend)
6. **Config file, env overrides, logging with secret redaction** (type:scaffold, area:backend)
7. **Database: SQLAlchemy 2.0, Alembic, SQLite WAL** (type:scaffold, area:backend)
8. **Auth: API key header and form login** (type:scaffold, area:backend)
9. **API error responses and request IDs** (type:scaffold, area:backend)
10. **HTTP client factory with per-provider rate limits and response cache** (type:scaffold, area:backend)
11. **Command queue, scheduler and SSE stream** (type:scaffold, area:backend)
12. **Scaffold frontend: Vite, React, TypeScript, TanStack, Biome, Vitest** (type:scaffold, area:frontend)
13. **Generated API client from OpenAPI** (type:scaffold, area:frontend)
14. **Dockerfile and entrypoint** (type:scaffold, area:infra)
15. **Dev stack compose: Prowlarr, qBittorrent, SABnzbd, Suwayomi, Kavita** (type:scaffold, area:infra)
16. **CI: lint, types, tests, image publish** (type:scaffold, area:infra)

## M1 Domain and parser

17. **Domain models: Series, Edition, Volume, Chapter, Episode, Mapping** (type:feature, area:backend)
18. **Chapter number normalization** (type:feature, area:parser)
19. **Release parser v1 with golden corpus** (type:feature, area:parser)
20. **Title matcher and Confidence** (type:feature, area:parser)

## M2 Metadata

21. **Provider interface and MangaBaka adapter** (type:feature, area:metadata)
22. **AniList adapter** (type:feature, area:metadata)
23. **MangaDex aggregate adapter** (type:feature, area:metadata)
24. **MangaUpdates adapter** (type:feature, area:metadata)
25. **Rakuten Books adapter** (type:feature, area:metadata)
26. **NDL search adapter** (type:feature, area:metadata)
27. **openBD adapter** (type:feature, area:metadata)
28. **Description chapter-range parser** (type:feature, area:parser)
29. **WEBTOON RSS adapter** (type:feature, area:metadata)
30. **Add series: resolve, suggest, override title and aliases** (type:feature, area:backend, area:frontend)
31. **RefreshSeriesMetadata command with provenance merge** (type:feature, area:metadata)

## M3 Gemini

32. **LLM interface and Gemini adapter** (type:feature, area:llm)
33. **TranslateSynopses command** (type:feature, area:llm)
34. **LLM fallbacks: chapter ranges and title disambiguation** (type:feature, area:llm)

## M4 Search and grab

35. **Prowlarr connection, indexer tag and categories** (type:feature, area:search)
36. **Direct Torznab and Newznab indexers** (type:feature, area:search)
37. **Quality profiles and the Decision engine** (type:feature, area:search)
38. **Monitor modes and Wanted** (type:feature, area:backend)
39. **SearchWanted command and interactive search** (type:feature, area:search, area:frontend)
40. **Pending review** (type:feature, area:search, area:frontend)
41. **RssSync command** (type:feature, area:search)
42. **qBittorrent adapter** (type:feature, area:search)
43. **SABnzbd adapter** (type:feature, area:search)
44. **Blocklist** (type:feature, area:search)

## M5 Import and library

45. **Import pipeline: extract, CBZ, ComicInfo.xml, rename, link** (type:feature, area:import)
46. **CheckDownloads command and failed downloads** (type:feature, area:import)
47. **Manual import** (type:feature, area:import, area:frontend)
48. **Existing library import** (type:feature, area:import, area:frontend)
49. **Kavita adapter: scan after import** (type:feature, area:import)

## M6 Suwayomi fallback

50. **Suwayomi adapter: connect, version check, auth** (type:feature, area:suwayomi)
51. **Source link for a series** (type:feature, area:suwayomi, area:frontend)
52. **FallbackToChapterSource command and Suwayomi import** (type:feature, area:suwayomi, area:import)

## M7 UI and ops

53. **Series detail page** (type:feature, area:frontend)
54. **Library, Wanted, Calendar and Activity pages** (type:feature, area:frontend)
55. **Settings pages** (type:feature, area:frontend)
56. **Backups** (type:feature, area:backend)
