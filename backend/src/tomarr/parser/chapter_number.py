import re
import unicodedata
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from enum import StrEnum

# These mirror Numeric(8, 3) on Chapter.number and Volume.number: three places
# and five integer digits.
DECIMAL_PLACES = 3
INTEGER_DIGITS = 5
_QUANTUM = Decimal(1).scaleb(-DECIMAL_PLACES)
_LIMIT = Decimal(10) ** INTEGER_DIGITS
# Quantizing follows the caller's decimal context unless it is pinned, so a low
# `prec` or an `Inexact` trap there would raise from a valid number. The extra
# digit holds 99999.9995, which rounds up to 100000.000 before it is refused.
_CONTEXT = Context(
    prec=INTEGER_DIGITS + DECIMAL_PLACES + 1, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation]
)

_ECHOED_TEXT_LIMIT = 80

_ONE_SHOT_WORDS = frozenset({"one-shot", "oneshot"})
_BARE_SPECIAL_WORDS = frozenset({"special", "extra", "omake", "bonus", "sp"})
_NOT_FINITE = re.compile(r"[+-]?(?:s?nan[0-9]*|inf(?:inity)?)")
_NEGATIVE = re.compile(r"-\s*[0-9]")
# Longest first: "chapter" and "ch." must be tried before "ch" and "c".
_PREFIX = re.compile(r"(?:chapter|episode|special|extra|ch\.|ch|sp|c)\s*", re.ASCII)
# A comma is a decimal separator only with one or two digits after it, so
# "1,000" stays a thousands separator and fails the patterns below.
_DECIMAL_COMMA = re.compile(r",(?=[0-9]{1,2}\Z)")
_PLAIN = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_PART = re.compile(r"(?P<whole>[0-9]+)(?:(?P<letter>[a-i])|\s*part\s*(?P<number>[1-9]))", re.ASCII)
_PART_LETTERS = "abcdefghi"


class ChapterNumberReason(StrEnum):
    EMPTY = "empty"
    NEEDS_POSITION = "needs_position"
    UNRECOGNIZED = "unrecognized"
    TOO_MANY_DECIMALS = "too_many_decimals"
    NEGATIVE = "negative"
    NOT_FINITE = "not_finite"
    TOO_LARGE = "too_large"


class InvalidChapterNumber(ValueError):
    def __init__(self, text: str, reason: ChapterNumberReason) -> None:
        # Both go to args so pickle and copy can rebuild the error.
        super().__init__(text, reason)
        self.text = text
        self.reason = reason

    def __str__(self) -> str:
        return f"invalid chapter number {self.text[:_ECHOED_TEXT_LIMIT]!r}: {self.reason}"


def normalize_chapter_number(text: str) -> Decimal:
    """Turn the text of a chapter number into a Decimal with exactly three places.

    `10`, `010`, `Ch.10`, `c10`, `Episode 10` and full-width digits all return
    `Decimal("10.000")`. `10,5` is 10.5. `One-shot` is 1. `Special 10.1` and
    `Extra 3` keep the number as written. A part marker adds tenths to a whole
    number: `10a` and `10 part 1` are 10.1, `10i` and `10 part 9` are 10.9. That is
    also what a real 10.1 gives, so the two cannot be told apart here. Superscript,
    circled and roman numerals are refused.

    Lists and ranges (`10,12`, `10-12`) must be split by the caller before calling,
    since `10,12` reads as 10.12.

    The input is `str`. A caller holding a number passes `repr(value)`, and a
    caller whose source reports "unknown" (Suwayomi uses a negative value) treats
    that as no chapter and does not call this.

    Raises InvalidChapterNumber, a ValueError whose `reason` says why:
    `empty`, `needs_position` (a special word with no number, whose place depends
    on the chapters around it), `unrecognized`, `negative`, `not_finite`,
    `too_large` (100000 or more) and `too_many_decimals` (a fourth place that
    changes the value, so `10.1000` is fine and `10.0001` is not). Nothing else
    is raised for any `str`.
    """
    # NFKC would turn superscript, circled and roman numerals into plain digits or
    # letters, so 10² would read as 102 and a roman numeral one as a part letter.
    # Full-width digits are decimal and still fold.
    if any(ch.isnumeric() and not ch.isdecimal() for ch in text):
        raise InvalidChapterNumber(text, ChapterNumberReason.UNRECOGNIZED)
    folded = unicodedata.normalize("NFKC", text).strip().lower()
    if not folded:
        raise InvalidChapterNumber(text, ChapterNumberReason.EMPTY)
    if folded in _ONE_SHOT_WORDS:
        folded = "1"
    if folded in _BARE_SPECIAL_WORDS:
        raise InvalidChapterNumber(text, ChapterNumberReason.NEEDS_POSITION)
    if _NOT_FINITE.fullmatch(folded):
        raise InvalidChapterNumber(text, ChapterNumberReason.NOT_FINITE)
    if _NEGATIVE.match(folded):
        raise InvalidChapterNumber(text, ChapterNumberReason.NEGATIVE)

    prefix = _PREFIX.match(folded)
    body = folded[prefix.end() :] if prefix else folded
    body = _DECIMAL_COMMA.sub(".", body)
    if _PLAIN.fullmatch(body):
        digits = body
    elif part := _PART.fullmatch(body):
        tenths = part["number"] or _PART_LETTERS.index(part["letter"]) + 1
        digits = f"{part['whole']}.{tenths}"
    else:
        raise InvalidChapterNumber(text, ChapterNumberReason.UNRECOGNIZED)

    value = Decimal(digits)
    # The range goes first: quantizing a very long digit string overflows the
    # decimal context, and 100000.0001 is more usefully "too large".
    if value >= _LIMIT:
        raise InvalidChapterNumber(text, ChapterNumberReason.TOO_LARGE)
    with localcontext(_CONTEXT):
        quantized = value.quantize(_QUANTUM)
    if quantized != value:
        raise InvalidChapterNumber(text, ChapterNumberReason.TOO_MANY_DECIMALS)
    return quantized
