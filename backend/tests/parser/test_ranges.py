from decimal import Decimal

import pytest

from tomarr.parser.chapter_number import ChapterNumberReason
from tomarr.parser.ranges import NumberList, parse_number_list
from tomarr.parser.release import NumberRange, Unparseable, UnparseableReason


def read(text: str) -> NumberList:
    result = parse_number_list(text)
    assert isinstance(result, NumberList)
    return result


def numbers(text: str) -> list[tuple[str, str]]:
    result = read(text)
    assert not result.ambiguous
    return [(str(r.start), str(r.end)) for r in result.ranges]


def guessed(text: str) -> list[tuple[str, str]]:
    result = read(text)
    assert result.ambiguous
    return [(str(r.start), str(r.end)) for r in result.ranges]


def refusal(text: str) -> Unparseable:
    result = parse_number_list(text)
    assert isinstance(result, Unparseable)
    assert result.reason is UnparseableReason.INVALID_NUMBER
    return result


def test_a_single_number_is_a_range_of_one() -> None:
    ten = NumberRange(Decimal("10.000"), Decimal("10.000"))
    assert parse_number_list("10") == NumberList((ten,))


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


@pytest.mark.parametrize(
    "joiner",
    [
        pytest.param("\u2010", id="hyphen"),
        pytest.param("\u2011", id="non-breaking hyphen"),
        pytest.param("\u2012", id="figure dash"),
        pytest.param("\u2013", id="en dash"),
        pytest.param("\u2014", id="em dash"),
        pytest.param("\u2015", id="horizontal bar"),
        pytest.param("\u2212", id="minus sign"),
        pytest.param("~", id="tilde"),
        pytest.param("\uff5e", id="full-width tilde"),
        pytest.param(" \u2013 ", id="spaced en dash"),
    ],
)
def test_dashes_and_tildes_make_a_range(joiner: str) -> None:
    assert numbers(f"10{joiner}12") == [("10.000", "12.000")]


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("1,000", [("1000.000", "1000.000")], id="one thousand"),
        pytest.param("1,100", [("1100.000", "1100.000")], id="no zero after the comma"),
        pytest.param("1,100-1,120", [("1100.000", "1120.000")], id="range"),
        pytest.param("1\uff0c100", [("1100.000", "1100.000")], id="full-width comma"),
    ],
)
def test_thousands_separator_is_read_as_one_number_and_marked_a_guess(
    text: str, expected: list[tuple[str, str]]
) -> None:
    assert guessed(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("1-20,181-240", [("1.000", "20.000"), ("181.000", "240.000")], id="ranges"),
        pytest.param("100,200", [("100.000", "100.000"), ("200.000", "200.000")], id="too large"),
        pytest.param("10,12", [("10.000", "10.000"), ("12.000", "12.000")], id="two digits"),
        pytest.param("01-05,041-124", [("1.000", "5.000"), ("41.000", "124.000")], id="zeros"),
        pytest.param("10, 120", [("10.000", "10.000"), ("120.000", "120.000")], id="space"),
    ],
)
def test_list_that_cannot_be_read_as_thousands_stays_a_list(
    text: str, expected: list[tuple[str, str]]
) -> None:
    assert numbers(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("10,5", [("10.000", "10.000"), ("5.000", "5.000")], id="descending pair"),
        pytest.param("1-5,3", [("1.000", "5.000"), ("3.000", "3.000")], id="inside a range"),
    ],
)
def test_list_going_backwards_is_marked_a_guess(text: str, expected: list[tuple[str, str]]) -> None:
    assert guessed(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("1 - 2000", [("1.000", "1.000")], id="2000"),
        pytest.param("3-2021", [("3.000", "3.000")], id="2021"),
        pytest.param("99-1900", [("99.000", "99.000")], id="lowest year"),
        pytest.param("0-2100", [("0.000", "0.000")], id="highest year"),
    ],
)
def test_range_ending_on_a_year_is_not_extended_and_is_marked_a_guess(
    text: str, expected: list[tuple[str, str]]
) -> None:
    assert guessed(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("100-2000", ("100.000", "2000.000"), id="start of 100"),
        pytest.param("1-1899", ("1.000", "1899.000"), id="end below the years"),
        pytest.param("1-2101", ("1.000", "2101.000"), id="end above the years"),
    ],
)
def test_range_that_cannot_end_on_a_year_is_kept(text: str, expected: tuple[str, str]) -> None:
    assert numbers(text) == [expected]


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
