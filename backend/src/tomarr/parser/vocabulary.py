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

# Neither a season count ("Season 1-5") nor an edition name ("Fullmetal
# Edition") is a group.
_NUMBERS_ONLY = re.compile(r"(?:seasons? )?[\d\s.\-]*")
_EDITION = re.compile(r"\bedition\b")
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
