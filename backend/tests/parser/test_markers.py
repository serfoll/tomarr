from decimal import Decimal
from time import perf_counter

import pytest

from tomarr.parser.chapter_number import ChapterNumberReason
from tomarr.parser.markers import Markers, read_numbers
from tomarr.parser.release import ChapterRange, NumberRange, Unparseable, UnparseableReason


def volume(start: str, end: str | None = None) -> NumberRange:
    return NumberRange(Decimal(start), Decimal(end or start))


def chapter(start: str, end: str | None = None, in_volume: str | None = None) -> ChapterRange:
    return ChapterRange(
        Decimal(start), Decimal(end or start), Decimal(in_volume) if in_volume else None
    )


def read(text: str) -> Markers:
    result = read_numbers(text)
    assert isinstance(result, Markers)
    return result


def short_id(text: str) -> str:
    return text[:40]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("Dandadan Vol. 3", volume("3"), id="Vol. 3"),
        pytest.param("Dandadan Vol.3", volume("3"), id="Vol.3"),
        pytest.param("Dandadan v03", volume("3"), id="v03"),
        pytest.param("Dandadan V1", volume("1"), id="V1"),
        pytest.param("Dandadan Volume 105", volume("105"), id="Volume 105"),
        pytest.param("Dandadan vol 15", volume("15"), id="vol 15"),
        pytest.param("Dandadan MANGA VOL 1-23", volume("1", "23"), id="upper case VOL"),
        pytest.param("Fullmetal Alchemist Volumes #01-27", volume("1", "27"), id="Volumes #01-27"),
        pytest.param("Dandadan v01-20", volume("1", "20"), id="volume range"),
        pytest.param("The Beginning After the End v08-v10", volume("8", "10"), id="v on both ends"),
        pytest.param("Dandadan Vol. 10.5", volume("10.5"), id="decimal volume"),
        pytest.param("第03巻", volume("3"), id="Japanese kan"),
        pytest.param("第０３巻", volume("3"), id="full-width digits"),
        pytest.param("第01-109巻", volume("1", "109"), id="Japanese kan range"),
        pytest.param("第1-23巻完", volume("1", "23"), id="Japanese kan then kanji"),
        pytest.param("カラー版 105巻", volume("105"), id="kan without dai"),
        pytest.param("Dandadan 3권", volume("3"), id="Korean gwon"),
        pytest.param("Dandadan 3卷", volume("3"), id="Chinese juan"),
        pytest.param("Dandadan 3册", volume("3"), id="Chinese ce"),
    ],
)
def test_volume_marker(text: str, expected: NumberRange) -> None:
    result = read(text)
    assert result.volumes == (expected,)
    assert result.chapters == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("Dandadan Ch. 12", chapter("12"), id="Ch. 12"),
        pytest.param("Dandadan Ch.12", chapter("12"), id="Ch.12"),
        pytest.param("Dandadan c010", chapter("10"), id="c010"),
        pytest.param("Dandadan ch0035", chapter("35"), id="ch0035"),
        pytest.param("One Piece - Chapter 1144", chapter("1144"), id="Chapter 1144"),
        pytest.param("One Piece Manga Chapters 1-535", chapter("1", "535"), id="Chapters range"),
        pytest.param("True Beauty c000-256", chapter("0", "256"), id="c000-256"),
        pytest.param("Dandadan c001-c010", chapter("1", "10"), id="c on both ends"),
        pytest.param("Dandadan Ch. 10.5", chapter("10.5"), id="decimal chapter"),
        pytest.param("Dandadan Ch. 10a", chapter("10.1"), id="part letter"),
        pytest.param("第12話", chapter("12"), id="Japanese wa"),
        pytest.param("第１２話", chapter("12"), id="full-width wa"),
        pytest.param("鏐 140-205話", chapter("140", "205"), id="wa range without dai"),
        pytest.param("Dandadan 12화", chapter("12"), id="Korean hwa"),
        pytest.param("Dandadan 12话", chapter("12"), id="simplified hua"),
        pytest.param("Dandadan 12話", chapter("12"), id="traditional hua"),
    ],
)
def test_chapter_marker(text: str, expected: ChapterRange) -> None:
    result = read(text)
    assert result.chapters == (expected,)
    assert result.volumes == ()


def test_ampersand_pack_gives_a_volume_range_and_a_chapter_range() -> None:
    result = read("One Piece Digital Colored Comics (v000-v105 & ch0035-1078)")
    assert result.volumes == (volume("0", "105"),)
    assert result.chapters == (chapter("35", "1078"),)


def test_version_before_batch_is_not_a_volume() -> None:
    result = read("Dandadan v2 batch")
    assert result.volumes == ()
    assert result.title_end == len("Dandadan v2 batch")


def test_volume_stating_its_chapters_gives_a_chapter_range_in_that_volume() -> None:
    result = read("Dandadan Vol. 3 Ch. 12-20")
    assert result.chapters == (chapter("12", "20", in_volume="3"),)
    assert result.volumes == ()


def test_pairing_applies_to_the_chapter_marker_straight_after() -> None:
    result = read("Dandadan Vol. 3, Ch. 12 Vol. 4 Ch. 30")
    assert result.chapters == (chapter("12", in_volume="3"), chapter("30", in_volume="4"))
    assert result.volumes == ()


def test_volume_range_before_a_chapter_marker_does_not_pair() -> None:
    result = read("Dandadan Vol. 3-4 Ch. 12")
    assert result.volumes == (volume("3", "4"),)
    assert result.chapters == (chapter("12"),)


def test_volume_far_from_a_chapter_marker_does_not_pair() -> None:
    result = read("Dandadan Vol. 3 Special Edition Ch. 12")
    assert result.volumes == (volume("3"),)
    assert result.chapters == (chapter("12"),)


def test_chapter_before_volume_does_not_pair() -> None:
    result = read("Dandadan Ch. 12 Vol. 3")
    assert result.volumes == (volume("3"),)
    assert result.chapters == (chapter("12"),)


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Dandadan v01-05,041-124", id="comma"),
        pytest.param("Dandadan v01-05 + 041-124", id="plus"),
    ],
)
def test_unmarked_range_after_a_volume_range_is_a_chapter_range(text: str) -> None:
    result = read(text)
    assert result.volumes == (volume("1", "5"),)
    assert result.chapters == (chapter("41", "124"),)


def test_single_volume_then_unmarked_chapters() -> None:
    result = read("Kagurabachi v01 + 009-056")
    assert result.volumes == (volume("1"),)
    assert result.chapters == (chapter("9", "56"),)


def test_chapter_list_keeps_every_piece() -> None:
    assert read("Dandadan Ch. 1-5, 8,10").chapters == (
        chapter("1", "5"),
        chapter("8"),
        chapter("10"),
    )


def test_plus_joins_chapter_pieces_like_a_comma() -> None:
    assert read("Dandadan Ch. 1-5 + 8").chapters == (chapter("1", "5"), chapter("8"))


def test_every_unmarked_piece_after_a_volume_is_a_chapter_range() -> None:
    result = read("Dandadan v01 + 009-056 + 100-120")
    assert result.volumes == (volume("1"),)
    assert result.chapters == (chapter("9", "56"), chapter("100", "120"))


def test_comma_in_a_chapter_marker_splits_and_is_never_a_decimal() -> None:
    assert read("Dandadan Ch. 10,5").chapters == (chapter("10"), chapter("5"))


def test_separate_markers_of_one_kind_collect_in_order() -> None:
    assert read("Dandadan v01, v03").volumes == (volume("1"), volume("3"))


def test_volume_marker_repeated_in_two_scripts_is_reported_once() -> None:
    result = read("ONE PIECE カラー版 105巻 ONE PIECE Volume 105 Colour")
    assert result.volumes == (volume("105"),)


@pytest.mark.parametrize(
    "text",
    [
        "Dandadan",
        "2001 Nights",
        "Look Back",
        "Dandadan 193.1 Bonus Chapter",
        "Re:Zero Volcano",
        "Chapterhouse Dune",
        "Level 5 Cheats",
        "Level5 Disc3 Marvel2",
        "Mob Psycho 100",
        "One Piece 1190",
        "Solo Leveling 13",
        "Omniscient Reader's Viewpoint 000-216",
        "Fullmetal Alchemist 01-13",
        "Hinokami Chronicles (v2026.03.26 & All DLC",
        "Season 2 Cover",
        pytest.param("", id="empty"),
    ],
    ids=short_id,
)
def test_text_without_a_marker_has_no_numbers(text: str) -> None:
    result = read(text)
    assert result.volumes == ()
    assert result.chapters == ()
    assert result.title_end == len(text)


@pytest.mark.parametrize(
    ("text", "expected_title"),
    [
        pytest.param("Dandadan, Vol. 3-5 by Yukinobu Tatsu", "Dandadan, ", id="comma before"),
        pytest.param("Dandadan v01-05,041-124 ", "Dandadan ", id="mixed pack"),
        pytest.param("One Piece - Chapter 1144", "One Piece - ", id="after a dash"),
        pytest.param("2001 Nights v03", "2001 Nights ", id="number in the title"),
        pytest.param("ワンピース 第115巻", "ワンピース ", id="kan"),
        pytest.param("Dandadan Vol. 3 Ch. 12-20", "Dandadan ", id="first of two markers"),
        pytest.param("Dandadan 12화", "Dandadan ", id="suffix marker starts at its digits"),
    ],
)
def test_title_ends_where_the_first_marker_starts(text: str, expected_title: str) -> None:
    assert text[: read(text).title_end] == expected_title


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        pytest.param("Dandadan Ch. 20-12", None, id="range ends below its start"),
        pytest.param("Dandadan v123456", ChapterNumberReason.TOO_LARGE, id="volume too large"),
        pytest.param("Dandadan c10.0001", ChapterNumberReason.TOO_MANY_DECIMALS, id="chapter"),
        pytest.param("Dandadan v01 + 20-12", None, id="continuation ends below its start"),
        pytest.param("Dandadan Vol. 3 Ch. 1-2-3", None, id="three ends"),
    ],
)
def test_number_error_comes_back_with_the_normalizer_reason(
    text: str, reason: ChapterNumberReason | None
) -> None:
    assert read_numbers(text) == Unparseable(UnparseableReason.INVALID_NUMBER, reason)


@pytest.mark.parametrize(
    ("text", "volumes", "chapters"),
    [
        pytest.param(
            "Dandadan v01-17 + 148-224 (2022-2026) (Digital) (1r0n)",
            (volume("1", "17"),),
            (chapter("148", "224"),),
            id="Dandadan plus",
        ),
        pytest.param(
            "Ao no Hako / Blue Box v01-20,181-240 (2022-2026) (Digital) (LuCaZ)",
            (volume("1", "20"),),
            (chapter("181", "240"),),
            id="Blue Box comma",
        ),
        pytest.param(
            "Kagurabachi v01-07,066-120 (2024-2026) (Digital) (LuCaZ)",
            (volume("1", "7"),),
            (chapter("66", "120"),),
            id="Kagurabachi",
        ),
        pytest.param(
            "One Piece - Digital Colored Comics+Cover Stories V1 Batch (v000-v105 & ch0035-1078)",
            (volume("0", "105"),),
            (chapter("35", "1078"),),
            id="One Piece batch version is not a volume",
        ),
        pytest.param(
            "Jujutsu Kaisen v00-30+Epilogue (Viz+TCB+innit)",
            (volume("0", "30"),),
            (),
            id="plus before a word",
        ),
        pytest.param(
            "One Piece Digital Colored Comics v001-v099 + Cover Stories",
            (volume("1", "99"),),
            (),
            id="plus before a word after v on both ends",
        ),
        pytest.param(
            "Demon Slayer: Kimetsu no Yaiba v1-23 by Koyoharu Gotouge [ENG / CBZ]",
            (volume("1", "23"),),
            (),
            id="by author",
        ),
        pytest.param(
            "One Piece, Vol.11 (VIZ Media LLC) by Eiichiro Oda [ENG / CBZ]",
            (volume("11"),),
            (),
            id="Vol.11 with publisher",
        ),
        pytest.param(
            "鋼の錬金術師 第00-27巻 [Fullmetal Alchemist vol 00-27]",
            (volume("0", "27"),),
            (),
            id="kan then the English vol",
        ),
        pytest.param(
            "[Kamizye] Omniscient Reader (Chapter 000-109) (Webtoon)",
            (),
            (chapter("0", "109"),),
            id="Chapter in parentheses",
        ),
    ],
)
def test_real_names(
    text: str, volumes: tuple[NumberRange, ...], chapters: tuple[ChapterRange, ...]
) -> None:
    result = read(text)
    assert result.volumes == volumes
    assert result.chapters == chapters


def test_comma_list_after_a_single_volume_reads_the_rest_as_chapters() -> None:
    result = read("Dandadan Vol. 1, 3, 5")
    assert result.volumes == (volume("1"),)
    assert result.chapters == (chapter("3"), chapter("5"))


def test_more_than_two_range_ends_in_a_longer_chain_still_fail() -> None:
    assert read_numbers("Dandadan Ch. 1-2-3-4") == Unparseable(UnparseableReason.INVALID_NUMBER)


@pytest.mark.parametrize("count", [25, 300])
def test_long_chapter_list_keeps_every_number(count: int) -> None:
    listed = ", ".join(str(number) for number in range(1, count + 1))
    result = read(f"Dandadan Ch. {listed}")
    assert result.chapters == tuple(chapter(str(number)) for number in range(1, count + 1))


def test_long_volume_list_with_a_suffix_marker_keeps_every_number() -> None:
    listed = ", ".join(str(number) for number in range(1, 26))
    result = read(f"Dandadan {listed}\u5dfb")
    assert result.volumes == tuple(volume(str(number)) for number in range(1, 26))


def test_long_loose_list_after_a_volume_keeps_every_chapter() -> None:
    listed = ", ".join(str(number) for number in range(10, 40))
    result = read(f"Dandadan v01, {listed}")
    assert result.volumes == (volume("1"),)
    assert result.chapters == tuple(chapter(str(number)) for number in range(10, 40))


@pytest.mark.parametrize("suffix", ["\u5dfb", "\u8a71", "\uad8c", "\ud654", "\u5377", "\u8bdd"])
@pytest.mark.parametrize("numbers", ["1-2-3", "1-2-3-4", "1-2-3-4-5", "\u7b2c1-2-3-4"])
def test_range_with_too_many_ends_before_a_suffix_marker_is_refused(
    numbers: str, suffix: str
) -> None:
    assert read_numbers(f"Dandadan {numbers}{suffix}") == Unparseable(
        UnparseableReason.INVALID_NUMBER
    )


def test_range_with_too_many_ends_after_a_marker_word_is_refused() -> None:
    assert read_numbers("Dandadan Ch. 1-2-3-4-5") == Unparseable(UnparseableReason.INVALID_NUMBER)


@pytest.mark.parametrize("text", ["Dandadan 1, 2, 3\u5dfb", "Dandadan \u7b2c1,2,3\u5dfb"])
def test_list_before_a_suffix_marker_is_all_volumes(text: str) -> None:
    result = read(text)
    assert result.volumes == (volume("1"), volume("2"), volume("3"))
    assert result.chapters == ()


def test_list_before_a_chapter_suffix_is_all_chapters() -> None:
    result = read("Dandadan 1, 2, 3\u8a71")
    assert result.chapters == (chapter("1"), chapter("2"), chapter("3"))
    assert result.volumes == ()


LONG = 20000
PIECES = LONG // 4
MAX_SECONDS = 0.5


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(" , ".join(["1"] * PIECES) + " x", id="spaced comma chain"),
        pytest.param(" - ".join(["1"] * PIECES) + " x", id="spaced hyphen chain"),
        pytest.param("v1 + " + " + ".join(["1"] * PIECES) + " x", id="chain after a marker"),
        pytest.param("Vol" + " " * LONG + "x", id="spaces after a marker word"),
        pytest.param("1" * LONG + "x", id="long digit run"),
        pytest.param("1 , " * PIECES + "12\u5dfb", id="chain ending in a suffix marker"),
    ],
)
def test_pathological_names_are_read_in_linear_time(text: str) -> None:
    started = perf_counter()
    read_numbers(text)
    assert perf_counter() - started < MAX_SECONDS
