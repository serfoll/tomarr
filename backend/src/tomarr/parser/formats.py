import re

from tomarr.parser.release import FileFormat
from tomarr.parser.vocabulary import FORMATS

# A name that is a file name ends in its extension, at times after a space.
_EXTENSION = re.compile(rf"\.\s?({'|'.join(FORMATS)})\Z", re.IGNORECASE)


def take_extension(name: str) -> tuple[str, FileFormat | None]:
    """Split a trailing file extension (`.zip`, `. zip`) off a name."""
    if extension := _EXTENSION.search(name):
        return name[: extension.start()], FORMATS[extension[1].lower()]
    return name, None
