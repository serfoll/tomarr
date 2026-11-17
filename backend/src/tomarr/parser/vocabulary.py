"""The words the tag reader knows: languages, file formats, and tag items that
say something about a release without naming its group."""

import re

from tomarr.parser.release import FileFormat

# ISO 639-2/B codes, because that is how names spell them (`FRE`, `GER`).
LANGUAGES = {
    "eng": "eng",
    "english": "eng",
    "jp": "jpn",
    "jpn": "jpn",
    "japanese": "jpn",
    "kor": "kor",
    "korean": "kor",
    "rus": "rus",
    "russian": "rus",
    "fre": "fre",
    "fr": "fre",
    "french": "fre",
    "vf": "fre",
    "ger": "ger",
    "german": "ger",
    "por": "por",
    "ita": "ita",
    "spa": "spa",
    "spanish": "spa",
    "multi": "mul",
}
FORMATS = {format.value: format for format in FileFormat}
# Seen next to a language in a tag, but not a format Tomarr imports.
OTHER_FORMATS = frozenset({"mobi", "jpg", "azw3", "txt"})

# Neither a season count ("Season 1-5"), an edition ("Fullmetal Edition", "15th
# anniversary book") nor a series position ("Demon Slayer #3", "n. 1") is a group.
_NUMBERS_ONLY = re.compile(r"(?:seasons? )?[\d\s.\-]*")
_EDITION = re.compile(r"\b(?:edition|anniversary)\b")
_SERIES_POSITION = re.compile(r"(?:#|\bn\. ?)\d+\Z")
_FILE_SIZE = re.compile(r"\d+(?:\.\d+)?\s?[kmgt]i?b")
_NOT_A_GROUP = frozenset(
    {
        "hq",
        "manga",
        "novel",
        "light novel",
        "complete",
        "ongoing",
        "scanlated",
        "upscaled",
        "reupload",
        "updated",
        "kobo optimised",
        "full",
        "web-novel",
        "fan-tl",
    }
)


def names_no_group(item: str) -> bool:
    """Whether a lowercase tag item is a number or a word that is never a group."""
    return bool(
        _NUMBERS_ONLY.fullmatch(item)
        or _FILE_SIZE.fullmatch(item)
        or item in _NOT_A_GROUP
        or _EDITION.search(item)
    )


def is_series_position(item: str) -> bool:
    """Whether a tag item gives a book's place in a series (`Demon Slayer #3`, `n. 1`).

    Such a tag names a series, not a group, even beside other items.
    """
    return _SERIES_POSITION.search(item) is not None
