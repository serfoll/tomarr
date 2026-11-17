import pytest

from tomarr.parser.formats import take_extension, take_format_words
from tomarr.parser.release import FileFormat


@pytest.mark.parametrize(
    ("text", "rest", "file_format"),
    [
        pytest.param(
            "Solo Leveling, Vol. 6 by Chugong EPUB",
            "Solo Leveling, Vol. 6 by Chugong",
            FileFormat.EPUB,
            id="trailing",
        ),
        pytest.param(
            "Demon Slayer MANGA VOL 1-23 PDF HIGH QUALITY",
            "Demon Slayer MANGA VOL 1-23 HIGH QUALITY",
            FileFormat.PDF,
            id="inside",
        ),
        pytest.param(
            "The Beginning After the End Volumes 1-8 epub",
            "The Beginning After the End Volumes 1-8",
            FileFormat.EPUB,
            id="lower case",
        ),
        pytest.param("Dandadan v01 CBZ CBR", "Dandadan v01", FileFormat.CBZ, id="first word wins"),
        pytest.param(
            "Art by Black Box.pdf by sing N song",
            "Art by Black Box.pdf by sing N song",
            None,
            id="part of a word",
        ),
        pytest.param("Zip Zap Vol. 1", "Zip Zap Vol. 1", None, id="zip is a title word"),
        pytest.param("Repdf Vol. 1", "Repdf Vol. 1", None, id="inside a longer word"),
    ],
)
def test_format_word_standing_alone_is_the_file_format(
    text: str, rest: str, file_format: FileFormat | None
) -> None:
    taken, found = take_format_words(text)
    assert " ".join(taken.split()) == rest
    assert found is file_format


def test_extension_is_split_off_the_end() -> None:
    assert take_extension("[Love-Saber] Solo Leveling.zip") == (
        "[Love-Saber] Solo Leveling",
        FileFormat.ZIP,
    )
