from itertools import product

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


def _expected(existing: Provenance, incoming: Provenance, locked: bool) -> bool:
    order = list(Provenance)
    if locked:
        return incoming is Provenance.USER
    return order.index(incoming) <= order.index(existing)


@pytest.mark.parametrize(
    ("existing", "incoming", "locked"),
    list(product(Provenance, Provenance, (False, True))),
)
def test_may_overwrite_over_the_full_table(
    existing: Provenance, incoming: Provenance, locked: bool
) -> None:
    assert may_overwrite(existing, incoming, locked) is _expected(existing, incoming, locked)


def test_lower_priority_is_refused() -> None:
    assert not may_overwrite(Provenance.MANGADEX_AGGREGATE, Provenance.INFERRED, locked=False)


def test_equal_priority_refreshes_its_own_value() -> None:
    assert may_overwrite(Provenance.INFERRED, Provenance.INFERRED, locked=False)


def test_higher_priority_wins() -> None:
    assert may_overwrite(Provenance.INFERRED, Provenance.DESCRIPTION_PARSE, locked=False)


def test_locked_refuses_everything_but_the_user() -> None:
    assert not may_overwrite(Provenance.USER, Provenance.MANGADEX_AGGREGATE, locked=True)
    assert may_overwrite(Provenance.INFERRED, Provenance.USER, locked=True)
    assert may_overwrite(Provenance.USER, Provenance.USER, locked=True)
