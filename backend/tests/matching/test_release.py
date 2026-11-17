from decimal import Decimal

from tomarr.matching.chapters import ProviderChapters
from tomarr.matching.confidence import Confidence
from tomarr.matching.matcher import TitleMatchReason
from tomarr.matching.release import Lowering, assess_release
from tomarr.matching.thresholds import Thresholds
from tomarr.parser.parse import parse_release
from tomarr.parser.release import ChapterRange, ParsedRelease, ReleaseWarning

THRESHOLDS = Thresholds(high=90, medium=70)


def parsed(name: str) -> ParsedRelease:
    outcome = parse_release(name)
    assert isinstance(outcome, ParsedRelease)
    return outcome


def chapters(*numbers: str) -> frozenset[Decimal]:
    return frozenset(Decimal(number) for number in numbers)


def test_clean_release_keeps_the_title_confidence() -> None:
    match = assess_release(parsed("Dandadan c041-050"), "Dandadan", [], THRESHOLDS, {})

    assert match.confidence is Confidence.HIGH
    assert match.score == 100
    assert match.matched == "Dandadan"
    assert match.reason is None
    assert match.lowered_by == ()
    assert match.unlisted_chapters == ()


def test_title_confidence_below_high_stays_there_when_clean() -> None:
    match = assess_release(
        parsed("Dandadan c041-050"), "Dandadam", [], Thresholds(high=100, medium=70), {}
    )

    assert match.confidence is Confidence.MEDIUM
    assert match.lowered_by == ()


def test_mixed_pack_lowers_one_tier() -> None:
    release = parsed("Dandadan v01-05,041-124")
    assert release.warnings == {ReleaseWarning.MIXED_PACK}

    match = assess_release(release, "Dandadan", [], THRESHOLDS, {})

    assert match.confidence is Confidence.MEDIUM
    assert match.lowered_by == (Lowering.UNCLEAN_PARSE,)


def test_no_numbers_lowers_one_tier() -> None:
    release = parsed("Dandadan")
    assert release.warnings == {ReleaseWarning.NO_NUMBERS}

    match = assess_release(release, "Dandadan", [], THRESHOLDS, {})

    assert match.confidence is Confidence.MEDIUM
    assert match.lowered_by == (Lowering.UNCLEAN_PARSE,)


def test_ambiguous_number_lowers_one_tier() -> None:
    release = parsed("Dandadan c10b")
    assert release.warnings == {ReleaseWarning.AMBIGUOUS_NUMBER}

    match = assess_release(release, "Dandadan", [], THRESHOLDS, {})

    assert match.confidence is Confidence.MEDIUM
    assert match.lowered_by == (Lowering.UNCLEAN_PARSE,)


def test_several_warnings_are_one_cause() -> None:
    release = ParsedRelease(
        title="Dandadan",
        warnings=frozenset({ReleaseWarning.NO_NUMBERS, ReleaseWarning.AMBIGUOUS_NUMBER}),
    )

    match = assess_release(release, "Dandadan", [], THRESHOLDS, {})

    assert match.confidence is Confidence.MEDIUM
    assert match.lowered_by == (Lowering.UNCLEAN_PARSE,)


def test_unlisted_decimal_lowers_one_tier_and_names_the_chapter() -> None:
    provider: ProviderChapters = {None: chapters("10", "11")}

    match = assess_release(parsed("Series c10.1"), "Series", [], THRESHOLDS, provider)

    assert match.confidence is Confidence.MEDIUM
    assert match.lowered_by == (Lowering.UNLISTED_DECIMAL,)
    assert match.unlisted_chapters == (Decimal("10.1"),)


def test_listed_decimal_does_not_lower() -> None:
    provider: ProviderChapters = {None: chapters("10", "10.1", "11")}

    match = assess_release(parsed("Series c10.1"), "Series", [], THRESHOLDS, provider)

    assert match.confidence is Confidence.HIGH
    assert match.lowered_by == ()
    assert match.unlisted_chapters == ()


def test_unclean_parse_with_unlisted_decimal_lands_on_low() -> None:
    release = parsed("Dandadan c10.1 (v2)")
    assert release.warnings
    provider: ProviderChapters = {None: chapters("10", "11")}

    match = assess_release(release, "Dandadan", [], THRESHOLDS, provider)

    assert match.confidence is Confidence.LOW
    assert match.lowered_by == (Lowering.UNCLEAN_PARSE, Lowering.UNLISTED_DECIMAL)
    assert match.unlisted_chapters == (Decimal("10.1"),)


def test_lowering_stops_at_low_from_a_medium_title() -> None:
    release = ParsedRelease(
        title="Dandadan",
        chapters=(ChapterRange(Decimal("10.1"), Decimal("10.1")),),
        warnings=frozenset({ReleaseWarning.NO_NUMBERS}),
    )
    provider: ProviderChapters = {None: chapters("10", "11")}

    match = assess_release(release, "Dandadam", [], Thresholds(high=100, medium=70), provider)

    assert match.confidence is Confidence.LOW
    assert match.lowered_by == (Lowering.UNCLEAN_PARSE, Lowering.UNLISTED_DECIMAL)


def test_decimal_in_a_named_volume_is_judged_against_that_volume() -> None:
    release = parsed("Series Vol. 3 Ch. 12.5")
    provider: ProviderChapters = {
        Decimal("3"): chapters("12", "13"),
        Decimal("4"): chapters("12.5"),
    }

    match = assess_release(release, "Series", [], THRESHOLDS, provider)

    assert match.confidence is Confidence.MEDIUM
    assert match.unlisted_chapters == (Decimal("12.5"),)


def test_volume_range_reads_chapters_from_its_volume() -> None:
    release = parsed("Series Vol. 3 Ch. 12-20")
    provider: ProviderChapters = {Decimal("3"): chapters(*(str(n) for n in range(12, 21)))}

    match = assess_release(release, "Series", [], THRESHOLDS, provider)

    assert match.confidence is Confidence.HIGH
    assert match.lowered_by == ()


def test_rejected_title_stays_rejected_and_reports_no_lowering() -> None:
    provider: ProviderChapters = {None: chapters("10", "11")}

    match = assess_release(parsed("One Piece Party c10.1"), "One Piece", [], THRESHOLDS, provider)

    assert match.confidence is None
    assert match.reason is TitleMatchReason.EXTRA_WORDS
    assert match.matched == "One Piece"
    assert match.lowered_by == ()
    assert match.unlisted_chapters == ()


def test_rejected_unclean_title_reports_no_lowering() -> None:
    match = assess_release(parsed("One Piece Party"), "One Piece", [], THRESHOLDS, {})

    assert match.confidence is None
    assert match.lowered_by == ()


def test_alias_match_is_reported() -> None:
    match = assess_release(parsed("Dan Da Dan c1"), "Dandadan", ["Dan Da Dan"], THRESHOLDS, {})

    assert match.confidence is Confidence.HIGH
    assert match.matched == "Dan Da Dan"
