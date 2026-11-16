from decimal import Decimal
from time import perf_counter

import pytest
from pytest import MonkeyPatch

from tomarr.parser import parse
from tomarr.parser.chapter_number import ChapterNumberReason
from tomarr.parser.parse import MAX_NAME_LENGTH, parse_release
from tomarr.parser.release import (
    ChapterRange,
    EditionHint,
    FileFormat,
    NumberRange,
    ParsedRelease,
    ReleaseWarning,
    Source,
    Unparseable,
    UnparseableReason,
)


def volume(start: str, end: str | None = None) -> NumberRange:
    return NumberRange(Decimal(start), Decimal(end or start))


def chapter(start: str, end: str | None = None, in_volume: str | None = None) -> ChapterRange:
    return ChapterRange(
        Decimal(start), Decimal(end or start), Decimal(in_volume) if in_volume else None
    )


def parsed(name: str) -> ParsedRelease:
    outcome = parse_release(name)
    assert isinstance(outcome, ParsedRelease)
    return outcome


def test_colored_digital_volume_with_language_and_format() -> None:
    release = parsed("One Piece, Vol. 106 (Colored) (Digital) by Eiichiro Oda [ENG / CBZ]")
    assert release.title == "One Piece"
    assert release.volumes == (volume("106"),)
    assert release.chapters == ()
    assert release.hints == frozenset({EditionHint.COLORED})
    assert release.source is Source.DIGITAL
    assert release.language == "eng"
    assert release.file_format is FileFormat.CBZ
    assert release.group is None
    assert release.clean


def test_colored_comics_in_the_title_is_colored_and_the_group_is_not_a_hint() -> None:
    release = parsed("One Piece - Digital Colored Comics v18 (2021) (Colored Council)")
    assert release.title == "One Piece - Digital Colored Comics"
    assert release.volumes == (volume("18"),)
    assert release.hints == frozenset({EditionHint.COLORED})
    assert release.group == "Colored Council"
    assert release.source is Source.UNKNOWN


def test_group_named_like_a_hint_is_not_a_hint() -> None:
    release = parsed("One Piece - Vol. 5 (2021) (Colored Council)")
    assert release.hints == frozenset()
    assert release.group == "Colored Council"


def test_webtoon_tag_is_a_hint() -> None:
    release = parsed("Only I Level Up / Solo Leveling [Webtoon] (2020-2023) (Digital) (LuCaZ)")
    assert release.title == "Only I Level Up / Solo Leveling"
    assert release.hints == frozenset({EditionHint.WEBTOON})
    assert release.group == "LuCaZ"
    assert release.source is Source.DIGITAL
    assert release.warnings == frozenset({ReleaseWarning.NO_NUMBERS})


def test_publisher_is_read_as_a_group_and_gives_no_hint() -> None:
    release = parsed("One Piece, Vol.3 (VIZ Media LLC) by Eiichiro Oda [ENG / CBZ]")
    assert release.group == "VIZ Media LLC"
    assert release.hints == frozenset()
    assert release.volumes == (volume("3"),)
    assert release.language == "eng"


def test_leading_group_tag() -> None:
    release = parsed("[Glitter] One Piece - Digital Colored Comics v001-099 (+ Cover Stories)")
    assert release.group == "Glitter"
    assert release.title == "One Piece - Digital Colored Comics"
    assert release.volumes == (volume("1", "99"),)


def test_title_is_the_text_before_the_first_marker() -> None:
    release = parsed("Demon Slayer: Kimetsu no Yaiba, Vol. 4 by Koyoharu Gotouge [ENG / CBZ]")
    assert release.title == "Demon Slayer: Kimetsu no Yaiba"


def test_title_loses_the_tags_in_front_of_it() -> None:
    release = parsed("[ENG] One Piece - Vol. 5 (FULL COLOR Digital Colored Comics)")
    assert release.title == "One Piece"
    assert release.language == "eng"
    assert release.group is None
    assert release.hints == frozenset({EditionHint.COLORED})


def test_japanese_volume_name_reads_the_alternate_title_marker_once() -> None:
    release = parsed("カグラバチ 第01-05巻 [Kagurabachi vol 01-05]")
    assert release.title == "カグラバチ"
    assert release.volumes == (volume("1", "5"),)
    assert release.group is None


def test_volume_range_and_loose_chapters_is_a_mixed_pack() -> None:
    release = parsed("Dandadan v01-05,041-124 (2022-2023) (Digital) (LuCaZ)")
    assert release.title == "Dandadan"
    assert release.volumes == (volume("1", "5"),)
    assert release.chapters == (chapter("41", "124"),)
    assert release.warnings == frozenset({ReleaseWarning.MIXED_PACK})
    assert not release.clean
    assert release.group == "LuCaZ"
    assert release.source is Source.DIGITAL


def test_ampersand_pack_inside_parentheses_is_a_mixed_pack() -> None:
    name = "One Piece - Digital Colored Comics+Cover Stories V1 Batch (v000-v105 & ch0035-1078)"
    release = parsed(name)
    # The name says both `V1 Batch` and `v000-v105`; the parser reports each marker.
    assert release.volumes == (volume("1"), volume("0", "105"))
    assert release.chapters == (chapter("35", "1078"),)
    assert release.warnings == frozenset({ReleaseWarning.MIXED_PACK})
    assert release.title == "One Piece - Digital Colored Comics+Cover Stories"
    assert release.group is None


def test_chapters_tagged_inside_parentheses_are_read() -> None:
    release = parsed("One Piece Manga (Chapters 1-50) by Eiichiro Oda [ENG / CBZ]")
    assert release.chapters == (chapter("1", "50"),)
    assert release.volumes == ()
    assert release.title == "One Piece Manga"
    assert release.group is None
    assert release.clean


def test_volume_with_its_own_chapters_is_not_a_mixed_pack() -> None:
    release = parsed("Dandadan Vol. 3 Ch. 12-20")
    assert release.chapters == (chapter("12", "20", in_volume="3"),)
    assert release.volumes == ()
    assert release.warnings == frozenset()


def test_only_chapters_with_no_volume_of_their_own_make_a_mixed_pack() -> None:
    release = parsed("Dandadan Vol. 3 Ch. 12-20 v5-8")
    assert release.volumes == (volume("5", "8"),)
    assert release.chapters == (chapter("12", "20", in_volume="3"),)
    assert release.warnings == frozenset()


def test_volume_range_alone_is_clean() -> None:
    release = parsed("Dandadan v01-20 (2022) (Digital) (LuCaZ)")
    assert release.warnings == frozenset()
    assert release.clean


def test_chapters_alone_are_clean() -> None:
    release = parsed("True Beauty c1-50 (2020-2023) (Digital) (angy)")
    assert release.chapters == (chapter("1", "50"),)
    assert release.warnings == frozenset()
    assert release.group == "angy"


def test_name_with_no_numbers_gets_the_no_numbers_warning() -> None:
    release = parsed("Demon Slayer: Kimetsu no Yaiba")
    assert release.title == "Demon Slayer: Kimetsu no Yaiba"
    assert release.warnings == frozenset({ReleaseWarning.NO_NUMBERS})
    assert not release.clean


def test_bare_number_stays_in_the_title_with_the_no_numbers_warning() -> None:
    release = parsed("One Piece 1190 (Digital)")
    assert release.title == "One Piece 1190"
    assert release.volumes == ()
    assert release.chapters == ()
    assert release.warnings == frozenset({ReleaseWarning.NO_NUMBERS})
    assert release.source is Source.DIGITAL


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("(Digital) (LuCaZ)", id="only tags"),
        pytest.param("Vol. 3", id="only a marker"),
        pytest.param("[LuCaZ] v01-05 (2022)", id="group and numbers"),
        pytest.param(" - ", id="only separators"),
    ],
)
def test_name_with_no_title_text_is_unparseable(name: str) -> None:
    assert parse_release(name) == Unparseable(UnparseableReason.NO_TITLE)


def test_video_name_is_unparseable() -> None:
    name = (
        "DAN DA DAN S02E08 You Can Do It Okarun 1080p CR WEB-DL DUAL AAC2.0 H 264-VARYG "
        "(Dandadan, Dual-Audio, Multi-Subs)"
    )
    assert parse_release(name) == Unparseable(UnparseableReason.VIDEO)


def test_audiobook_name_is_unparseable() -> None:
    name = "Rebirth: The Blue Box Heretic by T Carter [ENG / M4B]"
    assert parse_release(name) == Unparseable(UnparseableReason.AUDIOBOOK)


def test_rejected_name_reaches_no_other_code(monkeypatch: MonkeyPatch) -> None:
    def fail(*_: object) -> None:
        raise AssertionError("reached")

    monkeypatch.setattr(parse, "read_tags", fail)
    monkeypatch.setattr(parse, "read_numbers", fail)
    assert parse_release("Dandadan S02E08 1080p WEB-DL") == Unparseable(UnparseableReason.VIDEO)


def test_number_error_comes_back_with_the_normalizer_reason() -> None:
    assert parse_release("Dandadan v123456") == Unparseable(
        UnparseableReason.INVALID_NUMBER, ChapterNumberReason.TOO_LARGE
    )


def test_number_error_inside_a_tag_is_not_dropped() -> None:
    name = (
        "Demon Slayer -Kimetsu no Yaiba- Sweep the Board! "
        "(v16933346 & All DLCs) (Hypervisor|DenuvOwO)"
    )
    assert parse_release(name) == Unparseable(
        UnparseableReason.INVALID_NUMBER, ChapterNumberReason.TOO_LARGE
    )


@pytest.mark.parametrize(
    ("name", "language"),
    [
        pytest.param("One Piece 1190 [JP]", "jpn", id="JP"),
        pytest.param("Dandadan v01 [JPN]", "jpn", id="JPN"),
        pytest.param("Jujutsu Kaisen v01 [Korean]", "kor", id="Korean"),
        pytest.param("Dandadan v01 MULTi", "mul", id="MULTi"),
        pytest.param("Solo Leveling Vol. 1 [RUS / PDF]", "rus", id="RUS"),
        pytest.param("Dandadan Vol. 1", None, id="nothing said"),
        pytest.param("Dandadan Korean Edition Vol. 1", None, id="word in the title"),
    ],
)
def test_language_is_read_from_explicit_tags_only(name: str, language: str | None) -> None:
    assert parsed(name).language == language


def test_a_name_that_says_nothing_has_every_field_empty() -> None:
    release = parsed("Dandadan Vol. 3")
    assert release.group is None
    assert release.source is Source.UNKNOWN
    assert release.language is None
    assert release.hints == frozenset()
    assert release.file_format is None


def test_scan_source() -> None:
    release = parsed(
        "Monster: The Perfect Edition, Vol. 01-09 (2014-2016) (Scan) (HQ) "
        "by Naoki Urasawa [ENG / CBZ]"
    )
    assert release.source is Source.SCAN
    assert release.title == "Monster: The Perfect Edition"
    assert release.group is None


def test_name_at_the_length_limit_is_parsed() -> None:
    name = "Dandadan v01 " + "a" * (MAX_NAME_LENGTH - len("Dandadan v01 "))
    assert len(name) == MAX_NAME_LENGTH
    assert isinstance(parse_release(name), ParsedRelease)


def test_name_over_the_length_limit_is_refused_not_cut() -> None:
    name = "Dandadan v01 " + "a" * (MAX_NAME_LENGTH - len("Dandadan v01 ") + 1)
    assert parse_release(name) == Unparseable(UnparseableReason.TOO_LONG)


def test_long_spaced_chain_is_refused() -> None:
    name = "v1 " + " , ".join(["1"] * 1250) + " x"
    assert len(name) > 5000
    assert parse_release(name) == Unparseable(UnparseableReason.TOO_LONG)


def test_length_is_checked_before_anything_else(monkeypatch: MonkeyPatch) -> None:
    def fail(*_: object) -> None:
        raise AssertionError("reached")

    monkeypatch.setattr(parse, "rejection_reason", fail)
    assert parse_release("a" * (MAX_NAME_LENGTH + 1)) == Unparseable(UnparseableReason.TOO_LONG)


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("(" * 900, id="open parentheses"),
        pytest.param("[" * 900, id="open brackets"),
        pytest.param("()" * 450, id="empty parentheses"),
        pytest.param("[]" * 450, id="empty brackets"),
        pytest.param("([" * 450, id="alternating openers"),
        pytest.param("Dandadan " + "(v1) " * 180, id="marker tags"),
        pytest.param("Dandadan " + "[a (b] c) " * 90, id="crossed tags"),
        pytest.param("Dandadan v1 " + " , ".join(["1"] * 240) + " x", id="spaced chain"),
    ],
)
def test_pathological_names_are_parsed_in_linear_time(name: str) -> None:
    assert len(name) <= MAX_NAME_LENGTH
    started = perf_counter()
    parse_release(name)
    assert perf_counter() - started < 0.5
