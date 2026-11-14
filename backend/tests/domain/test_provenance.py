import pytest

from tomarr.domain.provenance import Provenance, may_overwrite


def test_priority_runs_from_user_down_to_inferred() -> None:
    assert list(Provenance) == [
        Provenance.USER,
        Provenance.MANGADEX_AGGREGATE,
        Provenance.DESCRIPTION_PARSE,
        Provenance.LLM_EXTRACTION,
        Provenance.INFERRED,
    ]
    assert [p.value for p in Provenance] == [
        "user",
        "mangadex_aggregate",
        "description_parse",
        "llm_extraction",
        "inferred",
    ]


USER, AGGREGATE, PARSE, LLM, INFERRED = (
    Provenance.USER,
    Provenance.MANGADEX_AGGREGATE,
    Provenance.DESCRIPTION_PARSE,
    Provenance.LLM_EXTRACTION,
    Provenance.INFERRED,
)

# Each row is the existing provenance, each column the incoming one, both in priority order.
# An unlocked value accepts an incoming provenance of equal or higher priority.
UNLOCKED = {
    USER: (True, False, False, False, False),
    AGGREGATE: (True, True, False, False, False),
    PARSE: (True, True, True, False, False),
    LLM: (True, True, True, True, False),
    INFERRED: (True, True, True, True, True),
}
# A locked value accepts only the user, whatever it holds.
LOCKED = {
    existing: (True, False, False, False, False)
    for existing in (USER, AGGREGATE, PARSE, LLM, INFERRED)
}

CASES = [
    (existing, incoming, locked, expected)
    for locked, table in ((False, UNLOCKED), (True, LOCKED))
    for existing, row in table.items()
    for incoming, expected in zip((USER, AGGREGATE, PARSE, LLM, INFERRED), row, strict=True)
]


@pytest.mark.parametrize(("existing", "incoming", "locked", "expected"), CASES)
def test_may_overwrite_over_the_full_table(
    existing: Provenance, incoming: Provenance, locked: bool, expected: bool
) -> None:
    assert may_overwrite(existing, incoming, locked) is expected
