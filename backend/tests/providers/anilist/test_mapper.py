import copy
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from tests.helpers.cassettes import recorded_response_body
from tomarr.domain.external_id import Provider
from tomarr.domain.series import Format
from tomarr.providers.anilist.mapper import parse_character_names, parse_search, parse_series

CASSETTES = (
    Path(__file__).parents[2] / "fixtures" / "cassettes" / "providers" / "anilist" / "test_client"
)
KOREAN_AND_CHINESE = "test_get_series_maps_a_korean_webtoon_and_a_chinese_series"

Payload = dict[str, object]


def recorded_body(name: str) -> Payload:
    return cast(Payload, recorded_response_body(CASSETTES / f"{name}.yaml"))


@pytest.fixture
def search_body() -> Payload:
    return recorded_body("test_search_returns_candidates_with_titles_format_and_cover")


@pytest.fixture
def series_body() -> Payload:
    return recorded_body("test_get_series_returns_the_series_by_its_id")


@pytest.fixture
def tower_of_god_body() -> Payload:
    return recorded_body(f"{KOREAN_AND_CHINESE}[tower-of-god]")


@pytest.fixture
def soul_land_body() -> Payload:
    return recorded_body(f"{KOREAN_AND_CHINESE}[soul-land]")


@pytest.fixture
def characters_body() -> Payload:
    return recorded_body("test_get_character_names_returns_main_characters_first")


def media_of(body: Payload) -> Payload:
    return cast(Payload, cast(Payload, body["data"])["Media"])


def search_media(body: Payload) -> list[Payload]:
    return cast(list[Payload], cast(Payload, cast(Payload, body["data"])["Page"])["media"])


def changed(body: Payload, **changes: object) -> Payload:
    """The lookup body with changes to its Media, leaving the recording itself alone."""
    result = copy.deepcopy(body)
    media_of(result).update(changes)
    return result


def tag(name: str, rank: int = 66, spoiler: bool = False) -> dict[str, object]:
    return {"name": name, "rank": rank, "isMediaSpoiler": spoiler}


def test_search_maps_every_recorded_result(search_body: Payload) -> None:
    candidates = parse_search(search_body)

    assert [candidate.provider_id for candidate in candidates] == ["118586", "173310", "179850"]
    assert {candidate.provider for candidate in candidates} == {Provider.ANILIST}
    assert all(isinstance(candidate.provider_id, str) for candidate in candidates)
    assert [candidate.external_ids for candidate in candidates] == [{}, {}, {}]


def test_frieren_carries_what_the_recording_shows(search_body: Payload) -> None:
    frieren = parse_search(search_body)[0]

    assert frieren.title == "Frieren: Beyond Journey\u2019s End"
    assert frieren.format is Format.MANGA
    assert frieren.status == "RELEASING"
    assert frieren.total_volumes is None
    assert frieren.total_chapters is None
    assert frieren.cover_url == (
        "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx118586-CXKgWikBFQgS.jpg"
    )


def test_totals_are_decimals_from_anilists_integers(search_body: Payload) -> None:
    anthology = parse_search(search_body)[1]

    assert anthology.total_volumes == Decimal(1)
    assert anthology.total_chapters == Decimal(5)
    assert isinstance(anthology.total_volumes, Decimal)


def test_aliases_are_the_other_titles_and_synonyms_without_repeats(search_body: Payload) -> None:
    frieren = parse_search(search_body)[0]

    assert frieren.aliases[:3] == (
        "Sousou no Frieren",
        "葬送のフリーレン",
        "Frieren at the Funeral",
    )
    assert frieren.title not in frieren.aliases
    assert len(set(frieren.aliases)) == len(frieren.aliases)
    assert "" not in frieren.aliases


def test_without_an_english_title_the_romaji_one_is_the_title_and_not_its_own_alias(
    search_body: Payload,
) -> None:
    anthology = parse_search(search_body)[1]

    assert anthology.title == "Sousou no Frieren Anthology"
    # The synonyms list the romaji title again.
    assert anthology.aliases == (
        "葬送のフリーレン アンソロジ",
        "Frieren: Beyond Journey\u2019s End Anthology",
        "Antología Frieren",
    )


def test_an_english_title_that_is_blank_falls_back_to_romaji(series_body: Payload) -> None:
    media = media_of(series_body)
    title = cast(Payload, media["title"])

    candidate = parse_series(changed(series_body, title={**title, "english": ""}))

    assert candidate.title == "Sousou no Frieren"
    assert "" not in candidate.aliases


def test_a_null_romaji_title_with_an_english_one_keeps_the_page(search_body: Payload) -> None:
    body = copy.deepcopy(search_body)
    frieren = search_media(body)[0]
    frieren["title"] = {**cast(Payload, frieren["title"]), "romaji": None}

    candidates = parse_search(body)

    assert len(candidates) == 3
    assert candidates[0].title == "Frieren: Beyond Journey\u2019s End"
    assert "Sousou no Frieren" not in candidates[0].aliases


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        pytest.param(
            {"english": "Frieren", "romaji": "Sousou no Frieren", "native": "葬送"},
            "Frieren",
            id="english",
        ),
        pytest.param(
            {"english": None, "romaji": "Sousou no Frieren", "native": "葬送"},
            "Sousou no Frieren",
            id="romaji",
        ),
        pytest.param({"english": None, "romaji": None, "native": "葬送"}, "葬送", id="native"),
        pytest.param({"english": " ", "romaji": "\t", "native": " 葬送 "}, "葬送", id="blanks"),
        pytest.param(
            {"english": "  Frieren  ", "romaji": None, "native": None}, "Frieren", id="stripped"
        ),
    ],
)
def test_the_title_is_the_first_usable_of_english_romaji_and_native(
    series_body: Payload, title: Payload, expected: str
) -> None:
    candidate = parse_series(changed(series_body, title=title))

    assert candidate.title == expected
    assert expected not in candidate.aliases


@pytest.mark.parametrize(
    "title",
    [
        pytest.param({"english": None, "romaji": None, "native": None}, id="null"),
        pytest.param({"english": "", "romaji": " ", "native": "\n"}, id="blank"),
    ],
)
def test_a_series_with_no_usable_title_is_refused(series_body: Payload, title: Payload) -> None:
    with pytest.raises(ValidationError, match="title"):
        parse_series(changed(series_body, title=title))


def test_blank_titles_and_synonyms_are_not_aliases_and_kept_ones_are_stripped(
    series_body: Payload,
) -> None:
    body = changed(
        series_body,
        title={"english": "  ", "romaji": "Sousou no Frieren", "native": " 葬送のフリーレン "},
        synonyms=["   ", "\t", " Frieren at the Funeral ", "Sousou no Frieren "],
    )

    candidate = parse_series(body)

    assert candidate.title == "Sousou no Frieren"
    assert candidate.aliases == ("葬送のフリーレン", "Frieren at the Funeral")


def test_get_series_maps_the_same_series_as_search(
    search_body: Payload, series_body: Payload
) -> None:
    assert parse_series(series_body) == parse_search(search_body)[0]


def test_the_recorded_novel_has_no_format(search_body: Payload) -> None:
    novel = parse_search(search_body)[2]

    assert novel.format is None
    assert novel.status == "FINISHED"
    assert novel.total_volumes == Decimal(2)
    assert novel.total_chapters == Decimal(10)


def test_the_largest_cover_is_taken_and_the_next_one_stands_in(series_body: Payload) -> None:
    cover = cast(Payload, media_of(series_body)["coverImage"])

    both = parse_series(changed(series_body, coverImage=cover))
    large_only = parse_series(changed(series_body, coverImage={**cover, "extraLarge": None}))
    neither = parse_series(changed(series_body, coverImage={"extraLarge": None, "large": None}))
    none = parse_series(changed(series_body, coverImage=None))

    assert both.cover_url == cover["extraLarge"]
    assert large_only.cover_url == cover["large"]
    assert neither.cover_url is None
    assert none.cover_url is None


def test_the_recorded_korean_series_with_a_long_strip_tag_is_a_webtoon(
    tower_of_god_body: Payload,
) -> None:
    tower_of_god = parse_series(tower_of_god_body)

    assert tower_of_god.provider_id == "85143"
    assert tower_of_god.format is Format.WEBTOON


def test_the_recorded_chinese_series_without_the_tag_is_manhua(soul_land_body: Payload) -> None:
    soul_land = parse_series(soul_land_body)

    assert soul_land.provider_id == "85446"
    assert soul_land.format is Format.MANHUA


def test_the_recorded_japanese_print_series_is_manga(series_body: Payload) -> None:
    assert parse_series(series_body).format is Format.MANGA


@pytest.mark.parametrize(
    ("media_format", "country", "tags", "expected"),
    [
        pytest.param("NOVEL", "JP", [], None, id="novel"),
        pytest.param("NOVEL", "KR", [tag("Long Strip")], None, id="novel-with-long-strip"),
        pytest.param("TV", "JP", [], None, id="anime-format"),
        pytest.param(None, "JP", [], None, id="no-format"),
        pytest.param("ONE_SHOT", "JP", [], Format.MANGA, id="one-shot"),
        pytest.param("MANGA", "JP", [], Format.MANGA, id="jp"),
        pytest.param("MANGA", "KR", [], Format.MANHWA, id="kr"),
        pytest.param("MANGA", "CN", [], Format.MANHUA, id="cn"),
        pytest.param("MANGA", "TW", [], Format.MANHUA, id="tw"),
        pytest.param("MANGA", "HK", [], Format.MANHUA, id="hk"),
        pytest.param("MANGA", "US", [], None, id="other-country"),
        pytest.param("MANGA", None, [], None, id="no-country"),
        pytest.param("MANGA", "KR", [tag("Long Strip", 79)], Format.WEBTOON, id="kr-strip-79"),
        pytest.param("MANGA", "KR", [tag("Long Strip", 20)], Format.WEBTOON, id="kr-strip-20"),
        pytest.param("MANGA", "JP", [tag("Long Strip", 20)], Format.WEBTOON, id="jp-strip-20"),
        pytest.param("MANGA", "CN", [tag("Long Strip", 20)], Format.WEBTOON, id="cn-strip-20"),
        pytest.param("MANGA", "US", [tag("Long Strip")], Format.WEBTOON, id="us-strip"),
        pytest.param("MANGA", None, [tag("Long Strip")], Format.WEBTOON, id="no-country-strip"),
        pytest.param("ONE_SHOT", "KR", [tag("Long Strip")], Format.WEBTOON, id="one-shot-strip"),
        pytest.param(
            "MANGA", "KR", [tag("Long Strip", 66, spoiler=True)], Format.MANHWA, id="kr-spoiler"
        ),
        pytest.param(
            "MANGA", "JP", [tag("Long Strip", 66, spoiler=True)], Format.MANGA, id="jp-spoiler"
        ),
        pytest.param(
            "MANGA",
            "KR",
            [tag("Long Strip", 66, spoiler=True), tag("Long Strip", 40)],
            Format.WEBTOON,
            id="spoiler-and-plain-strip",
        ),
        pytest.param("MANGA", "KR", [tag("Full Color")], Format.MANHWA, id="other-tag"),
        pytest.param("MANGA", "KR", None, Format.MANHWA, id="null-tags"),
    ],
)
def test_format_follows_the_rule_branch_by_branch(
    series_body: Payload,
    media_format: str | None,
    country: str | None,
    tags: list[dict[str, object]] | None,
    expected: Format | None,
) -> None:
    body = changed(series_body, format=media_format, countryOfOrigin=country, tags=tags)

    assert parse_series(body).format is expected


def test_a_series_where_anilist_left_everything_optional_null_maps_without_error(
    series_body: Payload,
) -> None:
    body = changed(
        series_body,
        title={"romaji": "Only Romaji", "english": None, "native": None},
        format=None,
        status=None,
        chapters=None,
        volumes=None,
        countryOfOrigin=None,
        coverImage=None,
        synonyms=None,
        tags=None,
    )

    candidate = parse_series(body)

    assert candidate.title == "Only Romaji"
    assert candidate.aliases == ()
    assert candidate.format is None
    assert candidate.status is None
    assert candidate.total_volumes is None
    assert candidate.total_chapters is None
    assert candidate.cover_url is None


def test_null_and_empty_synonyms_are_dropped(series_body: Payload) -> None:
    body = changed(series_body, synonyms=[None, "", "Frieren at the Funeral", None])

    assert parse_series(body).aliases[-1:] == ("Frieren at the Funeral",)
    assert "" not in parse_series(body).aliases


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"data": None}, id="data-null"),
        pytest.param({"data": {"Media": None}}, id="media-null"),
        pytest.param({"data": {"Media": {"id": 1}}}, id="missing-fields"),
        pytest.param([], id="not-an-object"),
    ],
)
def test_a_series_body_that_does_not_match_the_shape_is_refused(body: object) -> None:
    with pytest.raises(ValidationError):
        parse_series(body)


def test_an_errors_entry_refuses_the_body_even_when_the_data_is_there(
    series_body: Payload, search_body: Payload, characters_body: Payload
) -> None:
    error = [{"message": "Not Found.", "status": 404}]

    with pytest.raises(ValidationError, match="errors"):
        parse_series({**series_body, "errors": error})
    with pytest.raises(ValidationError, match="errors"):
        parse_search({**search_body, "errors": error})
    with pytest.raises(ValidationError, match="errors"):
        parse_character_names({**characters_body, "errors": error})


def test_a_search_with_no_match_is_an_empty_list() -> None:
    assert parse_search({"data": {"Page": {"media": []}}}) == []


def test_one_malformed_result_refuses_the_whole_page(search_body: Payload) -> None:
    body = copy.deepcopy(search_body)
    del search_media(body)[1]["id"]

    with pytest.raises(ValidationError):
        parse_search(body)


def test_character_names_keep_the_recorded_order_with_main_characters_first(
    characters_body: Payload,
) -> None:
    names = parse_character_names(characters_body)

    assert [name.full for name in names[:4]] == ["Frieren", "Fern", "Stark", "Heiter"]
    assert 0 < len(names) <= 25


def test_a_character_carries_its_native_name_and_alternatives(characters_body: Payload) -> None:
    names = {name.full: name for name in parse_character_names(characters_body)}

    assert names["Frieren"].native == "フリーレン"
    assert names["Frieren"].alternatives == ()
    assert names["Aura"].alternatives == (
        "Dantoudai no Aura (断頭台のアウラ)",
        "Aura the Guillotine",
    )


def test_a_character_with_null_parts_maps_without_error() -> None:
    body = {
        "data": {
            "Media": {
                "characters": {
                    "edges": [
                        {
                            "role": "MAIN",
                            "node": {"name": {"full": "A", "native": None, "alternative": None}},
                        },
                        {
                            "role": "MAIN",
                            "node": {
                                "name": {
                                    "full": "B",
                                    "native": "",
                                    "alternative": [None, "", "Bee"],
                                }
                            },
                        },
                    ]
                }
            }
        }
    }

    first, second = parse_character_names(body)

    assert (first.full, first.native, first.alternatives) == ("A", None, ())
    assert (second.full, second.native, second.alternatives) == ("B", None, ("Bee",))


def characters_with(*names: Payload) -> Payload:
    edges = [{"role": "MAIN", "node": {"name": name}} for name in names]
    return {"data": {"Media": {"characters": {"edges": edges}}}}


def test_a_character_with_only_a_native_name_keeps_it_as_its_name() -> None:
    body = characters_with({"full": None, "native": "フリーレン", "alternative": ["Frieren"]})

    (name,) = parse_character_names(body)

    assert (name.full, name.native, name.alternatives) == ("フリーレン", "フリーレン", ("Frieren",))


def test_a_character_with_no_usable_name_is_dropped() -> None:
    body = characters_with(
        {"full": None, "native": None, "alternative": ["Nameless"]},
        {"full": " ", "native": "\t", "alternative": []},
        {"full": "Fern", "native": None, "alternative": []},
    )

    assert [name.full for name in parse_character_names(body)] == ["Fern"]


def test_character_names_are_stripped_and_blank_ones_are_dropped() -> None:
    body = characters_with(
        {"full": "  Fern ", "native": "  ", "alternative": [" ", " Fern-chan ", "\n"]},
        {"full": " ", "native": " フリーレン ", "alternative": None},
    )

    fern, frieren = parse_character_names(body)

    assert (fern.full, fern.native, fern.alternatives) == ("Fern", None, ("Fern-chan",))
    assert (frieren.full, frieren.native) == ("フリーレン", "フリーレン")


def test_a_series_with_no_characters_gives_an_empty_list() -> None:
    assert parse_character_names({"data": {"Media": {"characters": {"edges": []}}}}) == []
