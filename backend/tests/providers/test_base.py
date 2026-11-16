from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.base import (
    CharacterName,
    SeriesCandidate,
    SeriesCharacters,
    SeriesLookup,
    SeriesSearch,
)


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


class CharactersOnlyAdapter:
    async def get_character_names(self, provider_id: str) -> list[CharacterName]:
        return []


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


def test_candidate_has_no_cover_by_default() -> None:
    assert make_candidate().cover_url is None


def test_candidate_holds_the_cover_it_is_given() -> None:
    candidate = replace(make_candidate(), cover_url="https://example.test/cover.jpg")

    assert candidate.cover_url == "https://example.test/cover.jpg"


def test_character_name_holds_its_names() -> None:
    name = CharacterName(full="Frieren", native="フリーレン", alternatives=("Frie", "Elf"))

    assert (name.full, name.native, name.alternatives) == (
        "Frieren",
        "フリーレン",
        ("Frie", "Elf"),
    )


def test_character_name_is_immutable() -> None:
    name = CharacterName(full="Frieren", native=None, alternatives=())

    with pytest.raises(FrozenInstanceError):
        name.full = "Fern"  # pyright: ignore[reportAttributeAccessIssue]


def test_characters_adapter_satisfies_characters_only() -> None:
    adapter = CharactersOnlyAdapter()

    assert isinstance(adapter, SeriesCharacters)
    assert not isinstance(adapter, SeriesSearch)
    assert not isinstance(adapter, SeriesLookup)


def test_search_adapter_does_not_satisfy_characters() -> None:
    assert not isinstance(SearchOnlyAdapter(), SeriesCharacters)
