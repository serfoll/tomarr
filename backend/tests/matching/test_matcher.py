import pytest
from rapidfuzz import fuzz

from tomarr.matching.confidence import Confidence
from tomarr.matching.matcher import TitleMatch, TitleMatchReason, match_title
from tomarr.matching.thresholds import Thresholds

ZERO_WIDTH_SPACE = chr(0x200B)
RIGHT_SINGLE_QUOTE = chr(0x2019)
LEFT_SINGLE_QUOTE = chr(0x2018)

DEFAULT = Thresholds(high=95, medium=85)


def test_exact_title_is_high() -> None:
    match = match_title("One Piece", "One Piece", [], DEFAULT)

    assert match == TitleMatch(Confidence.HIGH, 100, "One Piece", None)


def test_case_and_surrounding_whitespace_do_not_matter() -> None:
    match = match_title("  frieren ", "Frieren", [], DEFAULT)

    assert match.confidence is Confidence.HIGH
    assert match.score == 100


def test_punctuation_does_not_matter() -> None:
    match = match_title("Re Zero", "Re:Zero", [], DEFAULT)

    assert match.confidence is Confidence.HIGH
    assert match.matched == "Re:Zero"


@pytest.mark.parametrize("name", ["Jojo Bizarre Adventure", "Jojos Bizarre Adventure"])
def test_release_without_the_apostrophe_matches_the_possessive_title(name: str) -> None:
    match = match_title(name, "Jojo's Bizarre Adventure", [], DEFAULT)

    assert match.confidence is Confidence.HIGH
    assert match.reason is None


@pytest.mark.parametrize("apostrophe", ["'", RIGHT_SINGLE_QUOTE, LEFT_SINGLE_QUOTE])
def test_apostrophe_is_dropped_not_turned_into_a_word(apostrophe: str) -> None:
    match = match_title(f"Hell{apostrophe}s Paradise", "Hell Paradise", [], DEFAULT)

    assert match.reason is not TitleMatchReason.EXTRA_WORDS
    assert match.confidence is Confidence.HIGH


def test_trailing_zero_width_space_still_matches_at_high() -> None:
    match = match_title("Frieren" + ZERO_WIDTH_SPACE, "Frieren", [], DEFAULT)

    assert match == TitleMatch(Confidence.HIGH, 100, "Frieren", None)


def test_name_with_no_letters_or_digits_is_below_threshold() -> None:
    match = match_title("...", "?!", [], DEFAULT)

    assert match == TitleMatch(None, 0, None, TitleMatchReason.BELOW_THRESHOLD)


def test_alias_with_no_letters_or_digits_is_never_scored() -> None:
    match = match_title("!!!", "One Piece", ["?"], DEFAULT)

    assert match == TitleMatch(None, 0, None, TitleMatchReason.BELOW_THRESHOLD)


def test_best_alias_is_picked_and_reported_as_the_matched_name() -> None:
    match = match_title(
        "shingeki no kyojin",
        "Attack on Titan",
        ["Titan Attack", "Shingeki no Kyojin"],
        DEFAULT,
    )

    assert match.confidence is Confidence.HIGH
    assert match.matched == "Shingeki no Kyojin"


def test_title_wins_a_tie_with_an_alias() -> None:
    match = match_title("Frieren", "Frieren", ["frieren"], DEFAULT)

    assert match.matched == "Frieren"


def test_extra_words_in_the_name_are_rejected_without_confidence() -> None:
    match = match_title("One Piece Party", "One Piece", [], DEFAULT)

    assert match.confidence is None
    assert match.reason is TitleMatchReason.EXTRA_WORDS
    assert match.matched == "One Piece"


def test_missing_words_in_the_name_are_rejected_without_confidence() -> None:
    match = match_title("One Piece", "One Piece Party", [], DEFAULT)

    assert match.confidence is None
    assert match.reason is TitleMatchReason.MISSING_WORDS
    assert match.matched == "One Piece Party"


def test_extra_word_is_rejected_even_when_the_ratio_is_above_the_high_cutoff() -> None:
    title = "The Quintessential Quintuplets"
    name = "The Quintessential Quintuplets 2"
    assert fuzz.ratio(name.casefold(), title.casefold()) >= DEFAULT.high

    match = match_title(name, title, [], DEFAULT)

    assert match.confidence is None
    assert match.reason is TitleMatchReason.EXTRA_WORDS
    assert match.score >= DEFAULT.high


def test_word_checks_look_at_the_best_candidate_only() -> None:
    match = match_title("One Piece Party", "One Piece", ["One Piece Party"], DEFAULT)

    assert match.confidence is Confidence.HIGH
    assert match.matched == "One Piece Party"


def test_score_at_the_high_cutoff_is_high_and_just_under_is_medium() -> None:
    name, title = "Dandadan", "Dandadin"
    score = fuzz.ratio(name.casefold(), title.casefold())

    at_cutoff = match_title(name, title, [], Thresholds(high=score, medium=0))
    just_under = match_title(name, title, [], Thresholds(high=score + 1, medium=0))

    assert at_cutoff.confidence is Confidence.HIGH
    assert just_under.confidence is Confidence.MEDIUM
    assert at_cutoff.score == just_under.score == score


def test_score_at_the_medium_cutoff_is_medium_and_just_under_is_below_threshold() -> None:
    name, title = "Dandadan", "Dandadin"
    score = fuzz.ratio(name.casefold(), title.casefold())

    at_cutoff = match_title(name, title, [], Thresholds(high=100, medium=score))
    just_under = match_title(name, title, [], Thresholds(high=100, medium=score + 1))

    assert at_cutoff.confidence is Confidence.MEDIUM
    assert just_under.confidence is None
    assert just_under.reason is TitleMatchReason.BELOW_THRESHOLD
    assert just_under.matched == title


def test_unrelated_name_is_below_threshold() -> None:
    match = match_title("Berserk", "Vagabond", [], DEFAULT)

    assert match.confidence is None
    assert match.reason is TitleMatchReason.BELOW_THRESHOLD


def test_latin_name_against_hangul_only_series_is_a_different_script() -> None:
    match = match_title("One Piece", "원피스", ["원피스 (만화)"], DEFAULT)

    assert match == TitleMatch(None, 0, None, TitleMatchReason.DIFFERENT_SCRIPT)


def test_latin_alias_makes_a_series_comparable() -> None:
    match = match_title("One Piece", "원피스", ["One Piece"], DEFAULT)

    assert match.confidence is Confidence.HIGH
    assert match.matched == "One Piece"


def test_only_comparable_candidates_are_scored() -> None:
    match = match_title("원피스", "One Piece", ["원피스"], DEFAULT)

    assert match.confidence is Confidence.HIGH
    assert match.matched == "원피스"


def test_name_with_no_letters_is_comparable_with_every_title() -> None:
    match = match_title("86", "86", [], DEFAULT)

    assert match.confidence is Confidence.HIGH


def test_japanese_name_without_spaces_is_scored_not_word_checked() -> None:
    same = match_title("鬼滅の刃", "鬼滅の刃", [], DEFAULT)
    longer = match_title("ワンピース", "ワンピースパーティ", [], DEFAULT)

    assert same.confidence is Confidence.HIGH
    assert longer.confidence is None
    assert longer.reason is TitleMatchReason.BELOW_THRESHOLD
