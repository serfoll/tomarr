import re

from tomarr.parser.release import FileFormat
from tomarr.parser.vocabulary import FORMATS

# A name that is a file name ends in its extension, at times after a space.
_EXTENSION = re.compile(rf"\.\s?({'|'.join(FORMATS)})\Z", re.IGNORECASE)
_FORMAT_WORD = re.compile(r"(?<!\S)(cbz|cbr|pdf|epub)(?!\S)", re.IGNORECASE)


def take_extension(name: str) -> tuple[str, FileFormat | None]:
    """Split a trailing file extension (`.zip`, `. zip`) off a name."""
    if extension := _EXTENSION.search(name):
        return name[: extension.start()], FORMATS[extension[1].lower()]
    return name, None


def take_format_words(text: str) -> tuple[str, FileFormat | None]:
    """Remove the format words that stand alone in a name's text (`by Chugong EPUB`).

    The first one is the file format. `zip` and `rar` are left alone, since they
    can be title words.
    """
    found = _FORMAT_WORD.search(text)
    if found is None:
        return text, None
    return _FORMAT_WORD.sub(" ", text), FORMATS[found[1].lower()]
