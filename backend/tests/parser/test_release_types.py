from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from tomarr.parser.chapter_number import ChapterNumberReason
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


def test_release_with_no_warning_is_clean() -> None:
    assert ParsedRelease(title="One Piece").clean is True


@pytest.mark.parametrize("warning", list(ReleaseWarning))
def test_release_with_any_warning_is_not_clean(warning: ReleaseWarning) -> None:
    assert ParsedRelease(title="Dandadan", warnings=frozenset({warning})).clean is False


def test_defaults_describe_a_name_that_says_nothing() -> None:
    release = ParsedRelease(title="One Piece")
    assert release.volumes == ()
    assert release.chapters == ()
    assert release.group is None
    assert release.source is Source.UNKNOWN
    assert release.language is None
    assert release.hints == frozenset()
    assert release.file_format is None
    assert release.warnings == frozenset()


def test_chapter_range_volume_is_optional() -> None:
    three = Decimal(3)
    assert ChapterRange(start=Decimal(12), end=Decimal(20)).volume is None
    assert ChapterRange(start=Decimal(12), end=Decimal(20), volume=three).volume == three


def test_ranges_compare_by_value() -> None:
    assert NumberRange(Decimal(1), Decimal(2)) == NumberRange(Decimal(1), Decimal(2))
    assert NumberRange(Decimal(1), Decimal(2)) != NumberRange(Decimal(1), Decimal(3))


def test_parsed_release_is_frozen() -> None:
    release = ParsedRelease(title="One Piece")
    with pytest.raises(FrozenInstanceError):
        release.title = "Naruto"  # type: ignore[misc]


def test_unparseable_carries_the_normalizer_reason_or_none() -> None:
    bare = Unparseable(UnparseableReason.NO_TITLE)
    assert bare.number_reason is None
    with_number = Unparseable(UnparseableReason.INVALID_NUMBER, ChapterNumberReason.NEEDS_POSITION)
    assert with_number.number_reason is ChapterNumberReason.NEEDS_POSITION


def test_enum_values_are_the_names_the_corpus_and_ui_use() -> None:
    assert {r.value for r in UnparseableReason} == {
        "video",
        "audiobook",
        "game",
        "no_title",
        "invalid_number",
        "too_long",
    }
    assert {w.value for w in ReleaseWarning} == {"mixed_pack", "no_numbers", "ambiguous_number"}
    assert {s.value for s in Source} == {"digital", "scan", "unknown"}
    assert {h.value for h in EditionHint} == {"colored", "webtoon"}
    assert {f.value for f in FileFormat} == {"cbz", "cbr", "zip", "rar", "pdf", "epub"}
