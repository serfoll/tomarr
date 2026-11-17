from decimal import Decimal

from tomarr.matching.chapters import ProviderChapters, unlisted_decimals
from tomarr.parser.parse import parse_release
from tomarr.parser.release import ChapterRange, NumberRange, ParsedRelease


def parsed(name: str) -> ParsedRelease:
    outcome = parse_release(name)
    assert isinstance(outcome, ParsedRelease)
    return outcome


def chapters(*numbers: str) -> frozenset[Decimal]:
    return frozenset(Decimal(number) for number in numbers)


def numbers(*values: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(value) for value in values)


def test_decimals_between_listed_whole_chapters_are_unlisted() -> None:
    release = parsed("Dandadan Ch. 10.1-10.2")
    provider: ProviderChapters = {None: chapters("10", "11")}

    assert unlisted_decimals(release, provider) == numbers("10.1", "10.2")


def test_listed_decimal_is_not_unlisted() -> None:
    release = parsed("Dandadan Ch. 10.5")
    provider: ProviderChapters = {None: chapters("10", "10.5", "11")}

    assert unlisted_decimals(release, provider) == ()


def test_whole_chapter_missing_from_the_list_is_never_unlisted() -> None:
    release = parsed("Dandadan Ch. 12")
    provider: ProviderChapters = {None: chapters("10", "11", "13")}

    assert unlisted_decimals(release, provider) == ()


def test_range_checks_its_endpoints_only() -> None:
    release = ParsedRelease(
        title="Dandadan", chapters=(ChapterRange(Decimal("9.5"), Decimal("11")),)
    )
    provider: ProviderChapters = {None: chapters("9", "10", "11")}

    assert unlisted_decimals(release, provider) == numbers("9.5")


def test_result_is_sorted_and_deduplicated() -> None:
    release = ParsedRelease(
        title="Dandadan",
        chapters=(
            ChapterRange(Decimal("20.5"), Decimal("20.5")),
            ChapterRange(Decimal("10.1"), Decimal("10.1")),
            ChapterRange(Decimal("10.10"), Decimal("10.10")),
        ),
    )
    provider: ProviderChapters = {None: chapters("10", "11", "20", "21")}

    assert unlisted_decimals(release, provider) == numbers("10.1", "20.5")


def test_decimal_with_missing_whole_chapter_below_is_not_judged() -> None:
    release = parsed("Blue Box Ch. 105.5")
    provider: ProviderChapters = {None: chapters("104", "106")}

    assert unlisted_decimals(release, provider) == ()


def test_decimal_after_last_listed_chapter_is_not_judged() -> None:
    release = parsed("Blue Box Ch. 100.5")
    provider: ProviderChapters = {None: chapters("99", "100")}

    assert unlisted_decimals(release, provider) == ()


def test_decimal_outside_the_covered_range_is_not_unlisted() -> None:
    release = parsed("Blue Box Ch. 200.5")
    provider: ProviderChapters = {None: chapters(*(str(n) for n in range(1, 51)))}

    assert unlisted_decimals(release, provider) == ()


def test_named_volume_is_checked_only_against_its_own_chapters() -> None:
    release = parsed("Dandadan Vol. 3 Ch. 21.1")
    provider: ProviderChapters = {
        Decimal("3"): chapters("19", "20", "21"),
        Decimal("4"): chapters("22", "23"),
        None: chapters("21", "22"),
    }

    assert release.volumes == ()
    assert unlisted_decimals(release, provider) == ()


def test_volume_paired_with_chapter_narrows_the_check() -> None:
    release = parsed("Dandadan v03 c021.1")
    provider: ProviderChapters = {
        Decimal("3"): chapters("21", "22"),
        Decimal("4"): chapters("23", "24"),
    }

    assert unlisted_decimals(release, provider) == numbers("21.1")


def test_decimal_listed_in_another_volume_counts_as_unlisted_in_the_named_one() -> None:
    release = parsed("Dandadan Vol. 3 Ch. 21.1")
    provider: ProviderChapters = {
        Decimal("3"): chapters("21", "22"),
        Decimal("4"): chapters("21.1"),
    }

    assert unlisted_decimals(release, provider) == numbers("21.1")


def test_named_volume_with_empty_chapter_list_is_not_judged() -> None:
    release = parsed("Dandadan Vol. 3 Ch. 21.1")
    provider: ProviderChapters = {
        Decimal("3"): frozenset(),
        None: chapters("21", "22"),
    }

    assert unlisted_decimals(release, provider) == ()


def test_named_volume_missing_from_the_list_is_not_judged() -> None:
    release = parsed("Dandadan Vol. 3 Ch. 21.1")
    provider: ProviderChapters = {
        Decimal("2"): chapters("10", "11"),
        None: chapters("21", "22"),
    }

    assert unlisted_decimals(release, provider) == ()


def test_volume_range_names_every_provider_volume_it_spans() -> None:
    release = ParsedRelease(
        title="Dandadan",
        volumes=(NumberRange(Decimal("1"), Decimal("5")),),
        chapters=(ChapterRange(Decimal("8.5"), Decimal("8.5")),),
    )
    provider: ProviderChapters = {
        Decimal("2"): chapters("7", "8"),
        Decimal("3"): chapters("9", "10"),
        Decimal("6"): chapters("8.5"),
    }

    assert unlisted_decimals(release, provider) == numbers("8.5")


def test_volume_range_ignores_provider_volumes_outside_its_bounds() -> None:
    release = ParsedRelease(
        title="Dandadan",
        volumes=(NumberRange(Decimal("1"), Decimal("5")),),
        chapters=(ChapterRange(Decimal("40.5"), Decimal("40.5")),),
    )
    provider: ProviderChapters = {
        Decimal("1"): chapters("1", "2"),
        Decimal("6"): chapters("40", "41"),
    }

    assert unlisted_decimals(release, provider) == ()


def test_empty_provider_list_judges_nothing() -> None:
    assert unlisted_decimals(parsed("Dandadan Ch. 10.1"), {}) == ()


def test_no_volume_bucket_counts_when_the_release_names_no_volume() -> None:
    release = parsed("Dandadan Ch. 40.5")
    provider: ProviderChapters = {
        Decimal("5"): chapters("39", "40"),
        None: chapters("41"),
    }

    assert unlisted_decimals(release, provider) == numbers("40.5")
