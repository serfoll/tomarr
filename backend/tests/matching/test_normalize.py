import unicodedata

import pytest

from tomarr.matching.normalize import normalize_name

NO_BREAK_SPACE = chr(0xA0)
COMBINING_ACUTE = chr(0x301)
FULLWIDTH_ONE_PIECE = "ＯＮＥ ＰＩＥＣＥ"  # noqa: RUF001


def test_case_is_ignored() -> None:
    assert normalize_name("Frieren") == normalize_name("frieren")


def test_whitespace_runs_collapse_to_one_space() -> None:
    assert normalize_name("Sousou\tno" + NO_BREAK_SPACE + "Frieren") == "sousou no frieren"
    assert normalize_name("  Frieren \t ") == "frieren"
    assert normalize_name("a \n  b") == "a b"


def test_precomposed_and_combining_accents_match() -> None:
    assert normalize_name("café") == normalize_name("cafe" + COMBINING_ACUTE)


def test_fullwidth_letters_fold_to_ascii() -> None:
    assert normalize_name(FULLWIDTH_ONE_PIECE) == "one piece"


def test_casefold_result_is_still_nfkc() -> None:
    result = normalize_name("Straße ẞ İ")
    assert result.startswith("strasse ss")
    assert unicodedata.is_normalized("NFKC", result)


def test_punctuation_is_kept() -> None:
    assert normalize_name("Re:Zero") != normalize_name("Re Zero")
    assert normalize_name("Re:Zero") == "re:zero"


@pytest.mark.parametrize(
    "name", ["  " + FULLWIDTH_ONE_PIECE + " ", "Straße", "cafe" + COMBINING_ACUTE, "Re:ゼロ", ""]
)
def test_normalizing_twice_changes_nothing(name: str) -> None:
    once = normalize_name(name)
    assert normalize_name(once) == once


def test_empty_string_stays_empty() -> None:
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""
