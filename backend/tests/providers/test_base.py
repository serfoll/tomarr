from collections.abc import Mapping, Sequence
from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal

import pytest

from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.matching.thresholds import Thresholds
from tomarr.providers.base import (
    CharacterName,
    DatePrecision,
    SeriesCandidate,
    SeriesCharacters,
    SeriesLatestChapter,
    SeriesLookup,
    SeriesSearch,
    SeriesVolumeMetadata,
    SeriesVolumes,
    VolumeChapters,
    VolumeDetails,
    VolumeDetailsLookup,
    VolumeMetadata,
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


class VolumesOnlyAdapter:
    async def get_volume_chapters(self, provider_id: str) -> VolumeChapters:
        return {}


class LatestChapterOnlyAdapter:
    async def get_latest_chapter(self, provider_id: str) -> Decimal | None:
        return Decimal(139)


class VolumeMetadataOnlyAdapter:
    async def get_volume_metadata(
        self, title: str, aliases: Sequence[str], thresholds: Thresholds
    ) -> list[VolumeMetadata]:
        return []


def make_volume() -> VolumeMetadata:
    return VolumeMetadata(number=Decimal(1), isbn="9784098517718")


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


def test_volumes_adapter_satisfies_volumes_only() -> None:
    adapter = VolumesOnlyAdapter()

    assert isinstance(adapter, SeriesVolumes)
    assert not isinstance(adapter, SeriesSearch)
    assert not isinstance(adapter, SeriesLookup)


def test_search_adapter_does_not_satisfy_volumes() -> None:
    assert not isinstance(SearchOnlyAdapter(), SeriesVolumes)


def test_latest_chapter_adapter_satisfies_latest_chapter_only() -> None:
    adapter = LatestChapterOnlyAdapter()

    assert isinstance(adapter, SeriesLatestChapter)
    assert not isinstance(adapter, SeriesSearch)
    assert not isinstance(adapter, SeriesLookup)


def test_search_adapter_does_not_satisfy_latest_chapter() -> None:
    assert not isinstance(SearchOnlyAdapter(), SeriesLatestChapter)


def test_volume_metadata_adapter_satisfies_volume_metadata_only() -> None:
    adapter = VolumeMetadataOnlyAdapter()

    assert isinstance(adapter, SeriesVolumeMetadata)
    assert not isinstance(adapter, SeriesVolumes)
    assert not isinstance(adapter, SeriesSearch)


def test_volumes_adapter_does_not_satisfy_volume_metadata() -> None:
    assert not isinstance(VolumesOnlyAdapter(), SeriesVolumeMetadata)


def test_volume_metadata_has_only_what_it_is_given_by_default() -> None:
    volume = make_volume()

    assert volume.title is None
    assert volume.other_isbns == ()
    assert volume.release_date is None
    assert volume.release_precision is None
    assert volume.cover_url is None
    assert volume.synopsis is None
    assert volume.upcoming is False


def test_volume_metadata_holds_a_release_date_with_its_precision() -> None:
    volume = replace(
        make_volume(), release_date=date(2020, 8, 1), release_precision=DatePrecision.MONTH
    )

    assert (volume.release_date, volume.release_precision) == (
        date(2020, 8, 1),
        DatePrecision.MONTH,
    )


def test_volume_metadata_is_immutable() -> None:
    volume = make_volume()

    with pytest.raises(FrozenInstanceError):
        volume.isbn = "9784098517725"  # pyright: ignore[reportAttributeAccessIssue]


class VolumeDetailsOnlyAdapter:
    async def get_volume_details(self, isbns: Sequence[str]) -> Mapping[str, VolumeDetails]:
        return {}


def test_volume_details_adapter_satisfies_volume_details_lookup_only() -> None:
    adapter = VolumeDetailsOnlyAdapter()

    assert isinstance(adapter, VolumeDetailsLookup)
    assert not isinstance(adapter, SeriesVolumeMetadata)
    assert not isinstance(adapter, SeriesSearch)


def test_search_adapter_does_not_satisfy_volume_details_lookup() -> None:
    assert not isinstance(SearchOnlyAdapter(), VolumeDetailsLookup)


def test_volume_details_has_nothing_by_default() -> None:
    details = VolumeDetails()

    assert details.synopsis is None
    assert details.cover_url is None
    assert details.release_date is None
    assert details.release_precision is None


def test_volume_details_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        VolumeDetails().synopsis = "x"  # pyright: ignore[reportAttributeAccessIssue]
