# 0003: Volumes belong to Editions, Chapters belong to the Series

Status: accepted, November 2026

## Context

The same chapters are collected into volumes differently by different publications: Japanese tankōbon, English releases, 3-in-1 omnibuses. Sources disagree, and none of them is complete. Most tools store one flat volume list per series, so an omnibus or a wrong source corrupts it.

## Decision

- A Series has Chapters (decimal numbers) and one or more Editions. One Edition is primary.
- Volumes belong to an Edition. Which Chapters a Volume holds is a Mapping, stored per Edition.
- Every Mapping and every metadata field carries a Provenance. Priority: `user`, `mangadex_aggregate`, `description_parse`, `llm_extraction`, `inferred`. A refresh never overwrites a higher-priority value or a Locked one.
- Volume is optional, so webtoons are Chapters (with platform Episodes mapped onto them) and no Volumes.

## Consequences

- Omnibus and English splits are just more Editions. They don't touch the primary Edition's structure.
- The UI can show where every mapping came from and let the user lock it.
- More tables and joins than a flat list. Worth it, because this is the main thing Tomarr does better than its competitors.
- Comics and light novels fit later: an issue is a Chapter-like unit, a trade paperback is a Volume in an Edition.
