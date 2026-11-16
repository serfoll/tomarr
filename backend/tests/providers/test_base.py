from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.base import SeriesCandidate, SeriesLookup, SeriesSearch


def make_candidate() -> SeriesCandidate:
    return SeriesCandidate(
        provider=Provider.MANGABAKA,
        provider_id="1234",
        title="Sousou no Frieren",
        aliases=("Frieren: Beyond Journey's End", "葬送のフリーレン"),
        format=Format.MANGA,
        status="releasing",
        total_volumes=Decimal(14),
        total_chapters=Decimal("139.5"),
        external_ids={Provider.ANILIST: "118586", Provider.MANGAUPDATES: "9876"},
    )


class SearchOnlyAdapter:
    async def search(self, query: str) -> list[SeriesCandidate]:
        return [make_candidate()]


class SearchAndLookupAdapter(SearchOnlyAdapter):
    async def get_series(self, provider_id: str) -> SeriesCandidate:
        return make_candidate()


def test_candidate_is_immutable() -> None:
    candidate = make_candidate()

    with pytest.raises(FrozenInstanceError):
        candidate.title = "Another title"  # pyright: ignore[reportAttributeAccessIssue]


def test_search_only_adapter_satisfies_search_but_not_lookup() -> None:
    adapter = SearchOnlyAdapter()

    assert isinstance(adapter, SeriesSearch)
    assert not isinstance(adapter, SeriesLookup)


def test_adapter_with_both_methods_satisfies_both() -> None:
    adapter = SearchAndLookupAdapter()

    assert isinstance(adapter, SeriesSearch)
    assert isinstance(adapter, SeriesLookup)
