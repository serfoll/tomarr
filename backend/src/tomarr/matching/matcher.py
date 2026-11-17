import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz import fuzz

from tomarr.matching.confidence import Confidence
from tomarr.matching.normalize import normalize_name
from tomarr.matching.script import comparable, script_groups
from tomarr.matching.thresholds import Thresholds


class TitleMatchReason(StrEnum):
    EXTRA_WORDS = "extra_words"
    MISSING_WORDS = "missing_words"
    DIFFERENT_SCRIPT = "different_script"
    BELOW_THRESHOLD = "below_threshold"


@dataclass(frozen=True)
class TitleMatch:
    """How well a name fits a Series, or why it was refused.

    A refused name has no Confidence and carries the reason. `matched` is the title or
    Alias that scored best, and is None when no name shared the script of the query.
    """

    confidence: Confidence | None
    score: float
    matched: str | None
    reason: TitleMatchReason | None


def match_title(
    name: str, title: str, aliases: Sequence[str], thresholds: Thresholds
) -> TitleMatch:
    """Score a name against a Series title and its Aliases and keep the best.

    Token-set scores are not used: they rate `One Piece Party` against `One Piece` at 100.
    """
    query = _comparison_form(name)
    query_script = script_groups(query)
    best_name: str | None = None
    best_form = ""
    best_score = 0.0
    for candidate in (title, *aliases):
        form = _comparison_form(candidate)
        if not comparable(query_script, script_groups(form)):
            continue
        score = fuzz.ratio(query, form)
        if best_name is None or score > best_score:
            best_name, best_form, best_score = candidate, form, score

    if best_name is None:
        return TitleMatch(None, 0, None, TitleMatchReason.DIFFERENT_SCRIPT)

    query_words, best_words = set(query.split()), set(best_form.split())
    if best_words < query_words:
        return TitleMatch(None, best_score, best_name, TitleMatchReason.EXTRA_WORDS)
    if query_words < best_words:
        return TitleMatch(None, best_score, best_name, TitleMatchReason.MISSING_WORDS)
    if best_score >= thresholds.high:
        return TitleMatch(Confidence.HIGH, best_score, best_name, None)
    if best_score >= thresholds.medium:
        return TitleMatch(Confidence.MEDIUM, best_score, best_name, None)
    return TitleMatch(None, best_score, best_name, TitleMatchReason.BELOW_THRESHOLD)


def _comparison_form(text: str) -> str:
    # Punctuation becomes a space, so `Re:Zero` and `Re Zero` compare equal while
    # `normalize_name`, the Alias dedupe key, keeps them apart.
    spaced = "".join(
        " " if unicodedata.category(char).startswith("P") else char for char in normalize_name(text)
    )
    return " ".join(spaced.split())
