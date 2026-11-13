from enum import StrEnum


class Provenance(StrEnum):
    """Where a Mapping or a metadata value came from, highest priority first."""

    USER = "user"
    MANGADEX_AGGREGATE = "mangadex_aggregate"
    DESCRIPTION_PARSE = "description_parse"
    LLM_EXTRACTION = "llm_extraction"
    INFERRED = "inferred"


_RANK = {provenance: rank for rank, provenance in enumerate(Provenance)}


def may_overwrite(existing: Provenance, incoming: Provenance, locked: bool) -> bool:
    """Whether a write with `incoming` provenance may replace a value with `existing` provenance.

    Equal priority is allowed so a source can refresh its own earlier value. A Locked value
    accepts only the user. The rule covers the row it is on: adding a new row is never refused.
    """
    if locked:
        return incoming is Provenance.USER
    return _RANK[incoming] <= _RANK[existing]
