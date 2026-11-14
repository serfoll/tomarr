from decimal import Decimal

import pytest

from tomarr.parser.chapter_number import (
    ChapterNumberReason,
    InvalidChapterNumber,
    normalize_chapter_number,
)

EMPTY = ChapterNumberReason.EMPTY
NEEDS_POSITION = ChapterNumberReason.NEEDS_POSITION
UNRECOGNIZED = ChapterNumberReason.UNRECOGNIZED
TOO_MANY_DECIMALS = ChapterNumberReason.TOO_MANY_DECIMALS
NEGATIVE = ChapterNumberReason.NEGATIVE
NOT_FINITE = ChapterNumberReason.NOT_FINITE
TOO_LARGE = ChapterNumberReason.TOO_LARGE

HUGE = 5000


def assert_number(text: str, expected: str) -> None:
    result = normalize_chapter_number(text)
    assert isinstance(result, Decimal)
    assert str(result) == expected


def short_id(text: str) -> str:
    return repr(text) if len(text) <= 24 else f"{text[:12]!r} and {len(text)} characters"


def reason_of(text: str) -> ChapterNumberReason:
    with pytest.raises(InvalidChapterNumber) as caught:
        normalize_chapter_number(text)
    return caught.value.reason


# Accepted forms. Expected values are spelled with three places because every
# result is quantized to three places.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10", "10.000"),
        ("0", "0.000"),
        ("0.5", "0.500"),
        ("10.5", "10.500"),
        ("0.001", "0.001"),
        ("010", "10.000"),
        ("007.5", "7.500"),
        ("00000", "0.000"),
        ("10.050", "10.050"),
        ("10.005", "10.005"),
        ("  10  ", "10.000"),
    ],
)
def test_plain_numbers_and_leading_zeros(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10.1000", "10.100"),
        ("10.0050", "10.005"),
        ("0.0010", "0.001"),
        ("10.0", "10.000"),
    ],
)
def test_trailing_zeros_that_change_nothing_are_accepted(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ch.10", "10.000"),
        ("ch.10", "10.000"),
        ("Ch. 10", "10.000"),
        ("ch 10", "10.000"),
        ("ch10", "10.000"),
        ("Chapter 10", "10.000"),
        ("chapter10", "10.000"),
        ("CHAPTER 10", "10.000"),
        ("c10", "10.000"),
        ("C 10", "10.000"),
        ("Episode 10", "10.000"),
        ("EPISODE10", "10.000"),
        ("Ch.010.5", "10.500"),
        ("ch\t10", "10.000"),
        ("ch\n10", "10.000"),
        ("Ch.10a", "10.100"),
    ],
)
def test_prefixes_in_any_case_with_or_without_space(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Special 10.1", "10.100"),
        ("special10.1", "10.100"),
        ("Extra 3", "3.000"),
        ("extra3", "3.000"),
        ("sp 3", "3.000"),
        ("SP 3", "3.000"),
        ("sp10", "10.000"),
    ],
)
def test_numbered_specials_and_extras_keep_the_number_as_written(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize("text", ["One-shot", "Oneshot", "ONE-SHOT", " oneshot "])
def test_one_shot_is_chapter_one(text: str) -> None:
    assert_number(text, "1.000")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10,5", "10.500"),
        ("10,50", "10.500"),
        ("0,5", "0.500"),
        ("Ch.10,5", "10.500"),
    ],
)
def test_comma_is_a_decimal_separator_with_one_or_two_digits_after_it(
    text: str, expected: str
) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10a", "10.100"),
        ("10b", "10.200"),
        ("10c", "10.300"),
        ("10e", "10.500"),
        ("10i", "10.900"),
        ("10A", "10.100"),
        ("10 part 1", "10.100"),
        ("10 part 2", "10.200"),
        ("10 part 9", "10.900"),
        ("10 PART 2", "10.200"),
        ("10 Part 2", "10.200"),
        ("10part2", "10.200"),
        ("10 part2", "10.200"),
        ("10 part  2", "10.200"),
        ("010a", "10.100"),
        ("0a", "0.100"),
        ("99999i", "99999.900"),
    ],
)
def test_part_markers_add_tenths_to_a_whole_number(text: str, expected: str) -> None:
    assert_number(text, expected)


# Unicode. NFKC folds full-width forms and unusual spaces to ASCII before
# anything else looks at the text.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("\uff11\uff10\uff0e\uff15", "10.500", id="full-width digits and point"),
        pytest.param("\uff11\uff10\uff0c\uff15", "10.500", id="full-width comma"),
        pytest.param("\uff23\uff48\uff0e\uff11\uff10", "10.000", id="full-width letters"),
        pytest.param("\uff23\uff28\u3000\uff11\uff10", "10.000", id="ideographic space inside"),
        pytest.param("\u3000\uff11\uff10\u3000", "10.000", id="ideographic space around"),
        pytest.param("\u00a010\u00a0", "10.000", id="no-break space around"),
        pytest.param("ch\u00a010", "10.000", id="no-break space inside"),
        pytest.param("\t10\n", "10.000", id="tab and newline around"),
        pytest.param("10\u2002part\u20032", "10.200", id="en and em space in a part marker"),
        pytest.param("\u2467", "8.000", id="circled digit folds to a digit"),
        pytest.param("10\u00b2", "102.000", id="superscript digit folds to a digit"),
    ],
)
def test_nfkc_folds_these_forms_to_ascii(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("\u200b10", id="zero-width space before"),
        pytest.param("10\u200b", id="zero-width space after"),
        pytest.param("1\u200b0", id="zero-width space inside"),
        pytest.param("ch\u200b10", id="zero-width space after the prefix"),
        pytest.param("\u200b", id="zero-width space alone"),
        pytest.param("\ufeff10", id="byte order mark before"),
        pytest.param("10\u200d", id="zero-width joiner after"),
        pytest.param("1\u03010", id="combining acute inside"),
        pytest.param("10\u0301", id="combining acute after"),
        pytest.param("\u0661\u0660", id="arabic-indic digits"),
        pytest.param("\u0661\u0660.\u0665", id="arabic-indic digits with a point"),
        pytest.param("10.\u0665", id="arabic-indic digit after a point"),
        pytest.param("\u0661\u0660a", id="arabic-indic digits with a part marker"),
        pytest.param("\u0661\u0660 part 2", id="arabic-indic digits with a part word"),
        pytest.param("\u06f1\u06f0", id="extended arabic-indic digits"),
        pytest.param("\u0967\u0966", id="devanagari digits"),
        pytest.param("ch.\u0661\u0660", id="arabic-indic digits after a prefix"),
        pytest.param("10\u066b5", id="arabic decimal separator"),
        pytest.param("\u22121", id="unicode minus sign"),
        pytest.param("ch\u202810", id="line separator after the prefix"),
        pytest.param("ch\x8510", id="next line after the prefix"),
        pytest.param("ch\u168010", id="ogham space mark after the prefix"),
        pytest.param("10\u2028part 2", id="line separator before part"),
        pytest.param("\u00bd", id="vulgar fraction"),
        pytest.param("10\u00bd", id="whole number with a vulgar fraction"),
        pytest.param("\ud800", id="lone surrogate"),
        pytest.param("\x0010", id="nul before"),
    ],
)
def test_text_that_nfkc_and_strip_leave_unusual_is_unrecognized(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty string"),
        pytest.param(" ", id="space"),
        pytest.param("\t\n ", id="tab, newline and space"),
        pytest.param("\u00a0", id="no-break space"),
        pytest.param("\u3000\u3000", id="ideographic spaces"),
    ],
)
def test_blank_text_is_empty(text: str) -> None:
    assert reason_of(text) is EMPTY


# Words with no number.


@pytest.mark.parametrize(
    "text",
    [
        "Special",
        "Extra",
        "Omake",
        "Bonus",
        "SPECIAL",
        " extra ",
        "sp",
        "SP",
        "\uff2f\uff4d\uff41\uff4b\uff45",
    ],
)
def test_special_words_without_a_number_need_a_position(text: str) -> None:
    assert reason_of(text) is NEEDS_POSITION


@pytest.mark.parametrize(
    "text",
    ["Omake 3", "Bonus 3", "omake10", "special.", "extra:", "special 10.1 x", "specials 3"],
)
def test_omake_and_bonus_are_not_prefixes_and_special_words_must_stand_alone(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


# R1: prefix matching order. Prefixes overlap (chapter, ch., ch, c; special, sp)
# and the shorter one must not be taken when a longer one fits.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chapter10", "10.000"),
        ("chapter 10", "10.000"),
        ("ch.10", "10.000"),
        ("ch. 10", "10.000"),
        ("ch10", "10.000"),
        ("c10", "10.000"),
        ("special10", "10.000"),
        ("sp10", "10.000"),
        ("episode10", "10.000"),
        ("extra10", "10.000"),
    ],
)
def test_longest_prefix_wins_when_prefixes_overlap(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    "text",
    [
        "cherry",
        "cherry 10",
        "cherry10",
        "spring",
        "spring10",
        "extraordinary",
        "extraordinary 10",
        "chapterhouse",
        "chapterhouse 10",
        "cat10",
        "cat 10",
        "chx10",
        "spx10",
        "special_10",
        "episodes 10",
        "chapters 10",
        "specialist 10",
        "ch.x10",
        "c.10",
        "e10",
        "epi10",
    ],
)
def test_words_that_only_start_like_a_prefix_are_unrecognized(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


@pytest.mark.parametrize(
    "text",
    ["ch ch 10", "c ch 10", "ch.ch.10", "chapter ch 10", "c c10", "sp ch 10", "ch sp 10", "cc10"],
)
def test_two_prefixes_are_unrecognized(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


@pytest.mark.parametrize("text", ["c", "ch", "ch.", "chapter", "episode", "ch.  ", "c ."])
def test_a_prefix_with_no_number_is_unrecognized(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


@pytest.mark.parametrize("text", ["ch.-1", "c-1", "ch.nan", "chapter inf", "ch.+5", "sp-3"])
def test_what_follows_a_prefix_must_be_a_plain_number(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


# Strict pattern. Python's Decimal parses these, so only the pattern keeps them out.


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "1e3",
        "1E3",
        "1e-3",
        "1e+3",
        "1_000",
        "1_0.5",
        "0x10",
        "0b1",
        "+5",
        "+0",
        "10.",
        ".5",
        ".",
        "..",
        "10..5",
        "1.2.3",
        "10.5a",
        "10a2",
        "10aa",
        "10j",
        "10z",
        "10 a",
        "10 A",
        "a",
        "part 2",
        "10 part",
        "10 part 0",
        "10 part 10",
        "10 part 12",
        "10 part x",
        "10 parts 2",
        "10 part 2 part 3",
        "10-12",
        "10/5",
        "v10",
        "10 5",
        "one shot",
        "one-shot 1",
        "oneshots",
        "info",
        "nanny",
        "infinityx",
        "nan.5",
        "inf 10",
        "nan x",
        "1 0",
        "--1",
        "-",
    ],
)
def test_text_outside_the_strict_pattern_is_unrecognized(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


@pytest.mark.parametrize(
    "text",
    ["1,000", "1,0000", "1,000,000", "10,", ",5", "1,5,5", "1,,5", "10,5a", "1,5.5", "1.5,5"],
)
def test_commas_that_are_not_a_one_or_two_digit_decimal_are_unrecognized(text: str) -> None:
    assert reason_of(text) is UNRECOGNIZED


# R2: Decimal accepts these, so they are refused before it sees them.


@pytest.mark.parametrize(
    "text",
    [
        "NaN",
        "nan",
        "-nan",
        "+nan",
        "sNaN",
        "snan",
        "nan123",
        "Infinity",
        "infinity",
        "INFINITY",
        "-Infinity",
        "+Infinity",
        "inf",
        "INF",
        "+inf",
        "-inf",
        "\uff2e\uff41\uff2e",
    ],
)
def test_non_finite_words_are_not_finite(text: str) -> None:
    assert reason_of(text) is NOT_FINITE


# Negative numbers.


@pytest.mark.parametrize(
    "text", ["-1", "-0.5", "- 1", "-0", "-10a", "-1e3", "-100000", "-1.0001", "-1,5", "-\uff11"]
)
def test_a_leading_minus_on_a_number_is_negative(text: str) -> None:
    assert reason_of(text) is NEGATIVE


# Places.


@pytest.mark.parametrize(
    "text",
    [
        "10.0001",
        "10.1000000001",
        "0.0005",
        "0.0004",
        "00000.0004",
        "10.1001",
        "10.00001",
        "0.0000000000000000000000000000001",
    ],
)
def test_more_than_three_places_that_change_the_value_are_too_many_decimals(text: str) -> None:
    assert reason_of(text) is TOO_MANY_DECIMALS


# R3: the bound. Numeric(8, 3) has five integer digits, so 99999.999 is the top.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("99999.999", "99999.999"),
        ("99999.9990", "99999.999"),
        ("099999.999", "99999.999"),
        ("99999", "99999.000"),
        ("99999.5", "99999.500"),
    ],
)
def test_values_up_to_99999_999_are_accepted(text: str, expected: str) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    "text",
    [
        "100000",
        "100000.000",
        "100000.5",
        "100001",
        "9999999999",
        "0100000",
        "ch.100000",
        "100000a",
        "100000 part 1",
        "\uff11\uff10\uff10\uff10\uff10\uff10",
    ],
)
def test_100000_and_above_are_too_large(text: str) -> None:
    assert reason_of(text) is TOO_LARGE


# When an input has two problems, the order of the checks decides the reason.
# The order is: empty, one-shot, bare special word, not finite, negative,
# pattern, too large, too many decimals.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("100000.0001", TOO_LARGE),
        ("100000.9999999", TOO_LARGE),
        ("99999.9995", TOO_MANY_DECIMALS),
        ("99999.99951", TOO_MANY_DECIMALS),
        ("-Infinity", NOT_FINITE),
        ("-nan", NOT_FINITE),
        ("-1.0001", NEGATIVE),
        ("-100000", NEGATIVE),
        ("-1e3", NEGATIVE),
        ("100000.5a", UNRECOGNIZED),
        ("1e100000", UNRECOGNIZED),
        ("special", NEEDS_POSITION),
        ("   ", EMPTY),
    ],
)
def test_the_first_failing_check_names_the_reason(text: str, expected: ChapterNumberReason) -> None:
    assert reason_of(text) is expected


# R4: a part marker and a real decimal collide by design, and must not raise.


@pytest.mark.parametrize("text", ["10a", "10.1", "10 part 1", "10.100", "10.1000"])
def test_part_marker_and_real_decimal_give_the_same_number(text: str) -> None:
    assert normalize_chapter_number(text) == Decimal("10.100")
    assert str(normalize_chapter_number(text)) == "10.100"


# R5: long digit strings are checked by value, not parsed through int().


@pytest.mark.parametrize(
    "text",
    ids=short_id,
    argvalues=[
        "9" * HUGE,
        "9" * HUGE + ".5",
        "9" * HUGE + ".12345",
        "9" * HUGE + "a",
        "9" * HUGE + " part 2",
        "ch." + "9" * HUGE,
        "9" * HUGE + "," + "5",
        "1" + "0" * HUGE,
        "9" * HUGE + "." + "9" * HUGE,
    ],
)
def test_huge_whole_numbers_are_too_large(text: str) -> None:
    assert reason_of(text) is TOO_LARGE


@pytest.mark.parametrize(
    ("text", "expected"),
    ids=lambda value: short_id(value),
    argvalues=[
        ("0" * HUGE + "5", "5.000"),
        ("0" * HUGE + "5.5", "5.500"),
        ("0" * HUGE, "0.000"),
        ("0" * HUGE + ".5", "0.500"),
        ("0" * HUGE + "5a", "5.100"),
        ("1." + "0" * HUGE, "1.000"),
        ("0." + "0" * HUGE, "0.000"),
        ("1.5" + "0" * HUGE, "1.500"),
    ],
)
def test_huge_digit_strings_that_fit_the_range_and_places_are_accepted(
    text: str, expected: str
) -> None:
    assert_number(text, expected)


@pytest.mark.parametrize(
    "text",
    ids=short_id,
    argvalues=[
        "1." + "0" * HUGE + "1",
        "0." + "0" * HUGE + "1",
        "1." + "9" * HUGE,
        "99999." + "9" * HUGE,
        "0" * HUGE + "1." + "0" * HUGE + "1",
    ],
)
def test_huge_fractions_that_change_the_value_are_too_many_decimals(text: str) -> None:
    assert reason_of(text) is TOO_MANY_DECIMALS


@pytest.mark.parametrize(
    "text",
    ids=short_id,
    argvalues=[
        "-" + "9" * HUGE,
        "9" * HUGE + "x",
        "9" * HUGE + "e5",
        "ch" * HUGE,
        "ch." * HUGE + "1",
        "10a" * HUGE,
        "," * HUGE,
        "1" + "," * HUGE,
        "1," + "1" * HUGE,
        "\u200b" * HUGE,
        "\u0661" * HUGE,
        "nan" * HUGE,
    ],
)
def test_huge_hostile_text_is_refused_with_a_reason(text: str) -> None:
    assert isinstance(reason_of(text), ChapterNumberReason)


# The error.


def test_error_carries_the_reason_and_is_a_value_error() -> None:
    with pytest.raises(InvalidChapterNumber) as caught:
        normalize_chapter_number("10.0001")
    assert caught.value.reason is TOO_MANY_DECIMALS
    assert isinstance(caught.value, ValueError)


def test_error_message_names_the_input_and_the_reason() -> None:
    with pytest.raises(InvalidChapterNumber, match=r"'10\.0001'.*too_many_decimals"):
        normalize_chapter_number("10.0001")


def test_error_message_shows_the_text_as_given_not_as_folded() -> None:
    with pytest.raises(InvalidChapterNumber) as caught:
        normalize_chapter_number("\uff11\uff10\uff0e\uff10\uff10\uff10\uff11")
    assert "\uff11\uff10\uff0e\uff10\uff10\uff10\uff11" in str(caught.value)


def test_reasons_are_the_documented_strings() -> None:
    assert {reason.value for reason in ChapterNumberReason} == {
        "empty",
        "needs_position",
        "unrecognized",
        "too_many_decimals",
        "negative",
        "not_finite",
        "too_large",
    }


# Whatever the text, nothing except InvalidChapterNumber escapes, and a result
# is always a Decimal with three places inside the column's range.

HOSTILE = [
    "",
    " ",
    "\x00",
    "\x0010",
    "\ud800",
    "\udfff10",
    "\U0001f4a9",
    "\r\n",
    ".",
    "-",
    "+",
    "..",
    "e",
    "ch",
    "part",
    "10 part",
    "10 part ",
    "0x",
    "0e0",
    "1e999999999",
    "1e-999999999",
    "-1e999999999",
    "\ufb01",
    "\u0130",
    "\u017fp 3",
    "1\u0338",
    "\u2460\u2461\u2462",
    "\u00bd",
    "\u2153",
    "10\u20442",
    "\ufdfd",
    "\u212a",
    "1" * HUGE,
    "-" * HUGE,
    "ch." * 2000,
    "10a" * 1000,
    "9" * HUGE + "." + "9" * HUGE,
    " " * HUGE + "5",
    "5" + " " * HUGE,
    "5" + " " * HUGE + "5",
    "\u200b" * 100,
    "\u0661\u0660",
    "snan" + "9" * HUGE,
    "." * HUGE,
    "1" + "." * HUGE,
    "1," + "1," * HUGE,
]


@pytest.mark.parametrize("text", HOSTILE, ids=short_id)
def test_only_invalid_chapter_number_escapes(text: str) -> None:
    try:
        result = normalize_chapter_number(text)
    except InvalidChapterNumber as error:
        assert isinstance(error.reason, ChapterNumberReason)
    else:
        assert isinstance(result, Decimal)
        assert result.as_tuple().exponent == -3
        assert Decimal(0) <= result < Decimal(100000)
