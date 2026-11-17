from time import perf_counter

import pytest

from tomarr.parser.release import EditionHint, FileFormat, Source
from tomarr.parser.tags import read_tags


def without_tags(name: str) -> str:
    return " ".join(read_tags(name).text.split())


def test_tags_are_taken_out_of_the_text() -> None:
    name = "One Piece, Vol.3 (VIZ Media LLC) by Eiichiro Oda [ENG / CBZ]"
    assert without_tags(name) == "One Piece, Vol.3 by Eiichiro Oda"


def test_curly_tags_are_taken_out_of_the_text() -> None:
    name = "One Piece vN {+ the cover One-Shots} (Digital)"
    assert without_tags(name) == "One Piece vN"


def test_curly_tag_is_taken_out_even_when_it_looks_like_a_marker() -> None:
    name = "One Piece v012-023 (Colored) (Digital) (VLT) {Alabasta} {v1.0}"
    assert without_tags(name) == "One Piece v012-023"


def test_tag_holding_a_marker_stays_in_the_text() -> None:
    name = "Fullmetal Alchemist (v01-v27) (2005-2011) (Digital) (LostNerevarine-Empire)"
    assert without_tags(name) == "Fullmetal Alchemist v01-v27"


def test_alternate_title_tag_holding_a_marker_stays_in_the_text() -> None:
    name = "カグラバチ 第01-05巻 [Kagurabachi vol 01-05]"
    assert without_tags(name) == "カグラバチ 第01-05巻 Kagurabachi vol 01-05"


def test_tag_holding_a_bad_number_stays_in_the_text() -> None:
    assert "v123456" in read_tags("Dandadan (v123456)").text


@pytest.mark.parametrize(
    ("name", "language", "file_format"),
    [
        pytest.param("One Piece, Vol.3 [ENG / CBZ]", "eng", FileFormat.CBZ, id="ENG / CBZ"),
        pytest.param("Dandadan T1 [FRE / CBZ]", "fre", FileFormat.CBZ, id="FRE / CBZ"),
        pytest.param("Solo Leveling Vol. 1 [RUS / PDF]", "rus", FileFormat.PDF, id="RUS / PDF"),
        pytest.param("Hagane [JPN / CBZ]", "jpn", FileFormat.CBZ, id="JPN / CBZ"),
        pytest.param("Solo Leveling Vol. 1 [ENG / EPUB]", "eng", FileFormat.EPUB, id="EPUB"),
        pytest.param("Monster by Naoki Urasawa [ENG / CBR]", "eng", FileFormat.CBR, id="CBR"),
        pytest.param("Monster - Naoki Urasawa [CBZ ITA]", "ita", FileFormat.CBZ, id="CBZ ITA"),
        pytest.param("Solo Leveling [ENG / EPUB JPG]", "eng", FileFormat.EPUB, id="two formats"),
        pytest.param("Fullmetal Alchemist [ENG / MOBI]", "eng", None, id="format we do not read"),
        pytest.param(
            "Solo Leveling, Vol. 6 (light Novel) by Chugong [ENG / AZW3 EPUB MOBI]",
            "eng",
            FileFormat.EPUB,
            id="AZW3 EPUB MOBI",
        ),
        pytest.param("One Piece 1190 [JP]", "jpn", None, id="JP"),
        pytest.param("Jujutsu Kaisen [Korean]", "kor", None, id="Korean"),
        pytest.param("[ENG] One Piece - Vol. 5", "eng", None, id="leading ENG"),
        pytest.param("Fullmetal Alchemist Brotherhood [Multi]", "mul", None, id="Multi tag"),
        pytest.param("Dandadan v01 MULTi", "mul", None, id="MULTi word"),
        pytest.param("One Piece vN [VF]", "fre", None, id="VF"),
    ],
)
def test_language_and_format_are_read_from_tags(
    name: str, language: str, file_format: FileFormat | None
) -> None:
    tags = read_tags(name)
    assert tags.language == language
    assert tags.file_format is file_format


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("One Piece, Vol. 3", id="no tag"),
        pytest.param("Dandadan English Edition Vol. 1", id="language word in the title"),
        pytest.param("Korean Dandadan Vol. 1", id="Korean in the title"),
        pytest.param("French Kiss Vol. 1 [Group]", id="French in the title"),
        pytest.param("Dandadan [Webtoon]", id="tag that is not a language"),
    ],
)
def test_language_is_none_when_no_tag_says_it(name: str) -> None:
    tags = read_tags(name)
    assert tags.language is None
    assert tags.file_format is None


@pytest.mark.parametrize(
    ("name", "source"),
    [
        pytest.param("Dandadan v01 (2022) (Digital) (LuCaZ)", Source.DIGITAL, id="Digital"),
        pytest.param("Dandadan v01 (Digital SD) (KG Manga)", Source.DIGITAL, id="Digital SD"),
        pytest.param("Dandadan v01 [Digital] [Korean]", Source.DIGITAL, id="bracketed Digital"),
        pytest.param("Dandadan v01 (Webtoon, Digital)", Source.DIGITAL, id="among other items"),
        pytest.param("Monster, Vol. 01-09 (Scan) (HQ)", Source.SCAN, id="Scan"),
        pytest.param("Monster, Vol. 01-09 (Scans)", Source.SCAN, id="Scans"),
        pytest.param("Monster, Vol. 01-09 (Scan) (Digital)", Source.SCAN, id="first tag wins"),
        pytest.param("Dandadan Vol. 3 [ENG / CBZ]", Source.UNKNOWN, id="no source tag"),
        pytest.param("Digital Dandadan Vol. 3", Source.UNKNOWN, id="Digital in the title"),
        pytest.param("One Piece - Digital Colored Comics v18", Source.UNKNOWN, id="phrase"),
        pytest.param("Dandadan (Scanlated) (Flame Comics)", Source.UNKNOWN, id="Scanlated"),
        pytest.param("Dandadan (Flame Comics x Reaper Scans)", Source.UNKNOWN, id="Scans in name"),
    ],
)
def test_source_is_read_from_a_tag_standing_on_its_own(name: str, source: Source) -> None:
    assert read_tags(name).source is source


@pytest.mark.parametrize(
    ("name", "hints"),
    [
        pytest.param(
            "One Piece, Vol. 106 (Colored) (Digital)", {EditionHint.COLORED}, id="Colored"
        ),
        pytest.param("One Piece vN [Colored]", {EditionHint.COLORED}, id="bracketed Colored"),
        pytest.param("One Piece vN (Coloured)", {EditionHint.COLORED}, id="Coloured"),
        pytest.param(
            "[ENG] One Piece - Vol. 5 (FULL COLOR Digital Colored Comics)",
            {EditionHint.COLORED},
            id="Colored Comics inside a tag",
        ),
        pytest.param(
            "One Piece - Digital Colored Comics v18 (2021) (Colored Council)",
            {EditionHint.COLORED},
            id="Colored Comics in the title",
        ),
        pytest.param("Solo Leveling [Webtoon] (2020-2023)", {EditionHint.WEBTOON}, id="Webtoon"),
        pytest.param(
            "Solo Leveling Ch1-50 (Webtoon, CBZ)", {EditionHint.WEBTOON}, id="Webtoon, CBZ"
        ),
        pytest.param(
            "One Piece (Webtoon, Colored)",
            {EditionHint.WEBTOON, EditionHint.COLORED},
            id="two hints in one tag",
        ),
        pytest.param("One Piece - Chapter 5 (Colored Council)", set[EditionHint](), id="group"),
        pytest.param("Omniscient Reader (LINE Webtoon)", set[EditionHint](), id="LINE Webtoon"),
        pytest.param("Solo Leveling Webtoon Ch1-5", set[EditionHint](), id="Webtoon in the title"),
        pytest.param("The Colored Man Vol. 2", set[EditionHint](), id="Colored in the title"),
        pytest.param(
            "One Piece, Vol.3 (VIZ Media LLC) by Eiichiro Oda [ENG / CBZ]",
            set[EditionHint](),
            id="publisher",
        ),
    ],
)
def test_hints_come_from_a_tag_standing_on_its_own(name: str, hints: set[EditionHint]) -> None:
    assert read_tags(name).hints == frozenset(hints)


@pytest.mark.parametrize(
    ("name", "group"),
    [
        pytest.param(
            "[Glitter] One Piece - Digital Colored Comics v001-099", "Glitter", id="leading"
        ),
        pytest.param(
            "[260501][Maplestar] Solo Leveling - Full Animation", "Maplestar", id="after a date"
        ),
        pytest.param("[ENG] [LuCaZ] One Piece v5", "LuCaZ", id="after a language tag"),
        pytest.param("Dandadan v01 (2022) (Digital) (LuCaZ)", "LuCaZ", id="trailing"),
        pytest.param("Witch Hat Atelier v01-14 (2021) (Digital) (NrNn)", "NrNn", id="odd name"),
        pytest.param(
            "Jujutsu Kaisen (2018) (Digital) (NrNn, Rillant)", "NrNn, Rillant", id="two names"
        ),
        pytest.param(
            "One Piece, Vol.3 (VIZ Media LLC) by Eiichiro Oda [ENG / CBZ]",
            "VIZ Media LLC",
            id="publisher",
        ),
        pytest.param(
            "One Piece - Chapter 5 (2021) (Colored Council)",
            "Colored Council",
            id="named like a hint",
        ),
        pytest.param(
            "Dandadan (Scanlated) (Flame Comics) (Void) | Ongoing", "Void", id="last one wins"
        ),
        pytest.param(
            "[Unpaid Ferryman] Witch Hat Atelier Kitchen v1-3 (2021) (Digital) (LuCaZ)",
            "Unpaid Ferryman",
            id="leading wins",
        ),
        pytest.param(
            "[Suego (Suzuhiro)] Oyaji ga Ite (Jujutsu Kaisen) [Korean]",
            "Suego (Suzuhiro)",
            id="nested parentheses",
        ),
        pytest.param("Dandadan v01 [Group]", "Group", id="trailing bracket tag"),
        pytest.param(
            "Dandadan v01 [Yen Press][Stick]", "Stick", id="trailing bracket tags in a row"
        ),
        pytest.param(
            "Monster - Naoki Urasawa (1995-2001) [CBZ ITA] [1,85GB] [ImFilippo]",
            "ImFilippo",
            id="last of brackets and parentheses",
        ),
    ],
)
def test_group_is_the_leading_bracket_tag_or_the_last_trailing_tag(name: str, group: str) -> None:
    assert read_tags(name).group == group


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Dandadan v01 (2022) (Digital)", id="year and source only"),
        pytest.param("Dandadan v01 (2022-2023)", id="year range"),
        pytest.param("Dandadan (5)", id="number"),
        pytest.param("[ENG] One Piece - Vol. 5", id="language"),
        pytest.param("[ENG / CBZ] One Piece - Vol. 5", id="language and format"),
        pytest.param("One Piece, Vol. 106 (Colored) (Digital) (HQ) by Eiichiro Oda", id="quality"),
        pytest.param("Solo Leveling (Webtoon, Complete, 2020-2023) by Chugong", id="status words"),
        pytest.param("Jujutsu Kaisen (Manga)", id="Manga"),
        pytest.param("One Piece (Digital) (Upscaled) [Chapter 5]", id="Upscaled"),
        pytest.param("Dandadan 242 (2026) [reupload]", id="reupload"),
        pytest.param("Jujutsu Kaisen (Manga) [Updated]", id="Updated"),
        pytest.param("One Piece v012-023 (Colored) {Alabasta}", id="curly tag"),
        pytest.param("Fullmetal Alchemist (Fullmetal Edition) Volume 01", id="edition"),
        pytest.param("One Piece, Vol. 106 (Colored) (Kobo Optimised)", id="Kobo Optimised"),
        pytest.param("The Beginning After The End - Webtoon (Season 1-5)", id="season numbers"),
        pytest.param("One Piece - Vol. 3 (v1-v2)", id="marker tag"),
    ],
)
def test_group_is_none_when_no_tag_is_one(name: str) -> None:
    assert read_tags(name).group is None


def test_tags_hold_nothing_back_from_a_name_without_any() -> None:
    tags = read_tags("One Piece 1190")
    assert tags.text == "One Piece 1190"
    assert tags.group is None
    assert tags.hints == frozenset()


MAX_SECONDS = 0.5


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("(" * 900, id="open parentheses"),
        pytest.param("[" * 900, id="open brackets"),
        pytest.param("{" * 900, id="open braces"),
        pytest.param(")" * 900, id="close parentheses"),
        pytest.param("()" * 450, id="empty parentheses"),
        pytest.param("[]" * 450, id="empty brackets"),
        pytest.param("([" * 450, id="alternating openers"),
        pytest.param("[(" * 450 + ")]" * 450, id="nested"),
        pytest.param("(a" * 450, id="unclosed with text"),
        pytest.param("(" + "[a" * 450, id="paren then brackets"),
        pytest.param("(Digital) " * 100, id="repeated tags"),
        pytest.param("(v1) " * 180, id="repeated marker tags"),
        pytest.param("[" + "(" * 450 + "]" + ")" * 450, id="crossed"),
    ],
)
def test_pathological_tag_runs_are_read_in_linear_time(name: str) -> None:
    started = perf_counter()
    read_tags(name)
    assert perf_counter() - started < MAX_SECONDS
