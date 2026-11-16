from decimal import Decimal

import pytest

from tomarr.parser.chapter_number import ChapterNumberReason
from tomarr.parser.ranges import parse_number_list
from tomarr.parser.release import NumberRange, Unparseable, UnparseableReason


def numbers(text: str) -> list[tuple[str, str]]:
    result = parse_number_list(text)
    assert not isinstance(result, Unparseable)
    return [(str(r.start), str(r.end)) for r in result]


def refusal(text: str) -> Unparseable:
    result = parse_number_list(text)
    assert isinstance(result, Unparseable)
    assert result.reason is UnparseableReason.INVALID_NUMBER
    return result


def test_a_single_number_is_a_range_of_one() -> None:
    assert parse_number_list("10") == (NumberRange(Decimal("10.000"), Decimal("10.000")),)


def test_comma_list_is_separate_chapters_and_not_a_decimal() -> None:
    assert numbers("10,12") == [("10.000", "10.000"), ("12.000", "12.000")]


def test_comma_with_a_space_splits_too() -> None:
    assert numbers("10, 12") == [("10.000", "10.000"), ("12.000", "12.000")]


def test_full_width_comma_splits_like_an_ascii_comma() -> None:
    assert numbers("10\uff0c12") == [("10.000", "10.000"), ("12.000", "12.000")]


def test_hyphen_makes_one_range() -> None:
    assert numbers("10-12") == [("10.000", "12.000")]


def test_spaces_around_the_hyphen_are_allowed() -> None:
    assert numbers("10 - 12") == [("10.000", "12.000")]


def test_full_width_hyphen_makes_a_range() -> None:
    assert numbers("10\uff0d12") == [("10.000", "12.000")]


def test_range_and_loose_number_are_two_ranges() -> None:
    assert numbers("10-12,15") == [("10.000", "12.000"), ("15.000", "15.000")]


def test_decimal_numbers_inside_a_range() -> None:
    assert numbers("10.5-12.5") == [("10.500", "12.500")]


def test_a_range_may_start_and_end_on_the_same_number() -> None:
    assert numbers("10-10") == [("10.000", "10.000")]


def test_full_width_digits_pass() -> None:
    assert numbers("\uff11\uff10-\uff11\uff12") == [("10.000", "12.000")]


def test_prefixed_numbers_pass() -> None:
    assert numbers("Ch.10") == [("10.000", "10.000")]
    assert numbers("Ch.10-Ch.12") == [("10.000", "12.000")]
    assert numbers("c010-c012,c015") == [("10.000", "12.000"), ("15.000", "15.000")]


def test_part_letters_survive_a_range() -> None:
    assert numbers("10a-12") == [("10.100", "12.000")]


def test_ascii_one_shot_is_chapter_one_and_is_not_split_at_its_hyphen() -> None:
    assert numbers("One-shot") == [("1.000", "1.000")]


def test_full_width_one_shot_hyphen_still_reads_as_chapter_one() -> None:
    assert numbers("one\uff0dshot") == [("1.000", "1.000")]


@pytest.mark.parametrize("text", ["12-10", "10.5-10.4", "12-ch.10"])
def test_range_ending_below_its_start_is_refused(text: str) -> None:
    result = refusal(text)
    assert result.number_reason is None


def test_range_with_three_ends_is_refused() -> None:
    assert refusal("10-12-14").number_reason is None


@pytest.mark.parametrize("text", ["10,,12", "10,", ",10", "10-", "10-,12", "", "  "])
def test_empty_piece_is_refused_with_the_empty_reason(text: str) -> None:
    assert refusal(text).number_reason is ChapterNumberReason.EMPTY


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("one shot", ChapterNumberReason.UNRECOGNIZED),
        ("one\u2011shot", ChapterNumberReason.UNRECOGNIZED),
        ("one\u2010shot", ChapterNumberReason.UNRECOGNIZED),
        ("Special", ChapterNumberReason.NEEDS_POSITION),
        ("Extra", ChapterNumberReason.NEEDS_POSITION),
        ("Omake", ChapterNumberReason.NEEDS_POSITION),
        ("Bonus", ChapterNumberReason.NEEDS_POSITION),
        ("-1", ChapterNumberReason.NEGATIVE),
        ("10--12", ChapterNumberReason.NEGATIVE),
        ("10.0001", ChapterNumberReason.TOO_MANY_DECIMALS),
        ("100000", ChapterNumberReason.TOO_LARGE),
        ("10²", ChapterNumberReason.UNRECOGNIZED),
    ],
)
def test_normalizer_refusals_come_back_with_their_reason(
    text: str, reason: ChapterNumberReason
) -> None:
    assert refusal(text).number_reason is reason


def test_a_bad_piece_after_a_good_one_is_still_refused() -> None:
    assert refusal("10,Special").number_reason is ChapterNumberReason.NEEDS_POSITION
    assert refusal("10-12,Extra").number_reason is ChapterNumberReason.NEEDS_POSITION
