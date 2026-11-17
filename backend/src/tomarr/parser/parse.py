import re

from tomarr.parser.markers import read_numbers
from tomarr.parser.media import rejection_reason
from tomarr.parser.release import (
    ParsedRelease,
    ParseOutcome,
    ReleaseWarning,
    Unparseable,
    UnparseableReason,
)
from tomarr.parser.tags import read_tags
from tomarr.parser.vocabulary import LANGUAGES

# The longest real name in the raw corpus is 261 characters. Names are untrusted
# indexer text, so a longer one is refused instead of scanned.
MAX_NAME_LENGTH = 1000
_TITLE_EDGES = " -,|/:&+"
# Read only after the title, so a title such as "MULTi Man" says no language.
_MULTI_WORD = re.compile(r"\bMULTi\b")


def parse_release(name: str) -> ParseOutcome:
    if len(name) > MAX_NAME_LENGTH:
        return Unparseable(UnparseableReason.TOO_LONG)
    name = name.strip()
    if (reason := rejection_reason(name)) is not None:
        return Unparseable(reason)
    tags = read_tags(name)
    numbers = read_numbers(tags.text)
    if isinstance(numbers, Unparseable):
        return numbers
    title = " ".join(tags.text[: numbers.title_end].split()).strip(_TITLE_EDGES)
    if not title:
        return Unparseable(UnparseableReason.NO_TITLE)

    warnings: set[ReleaseWarning] = set()
    if not numbers.volumes and not numbers.chapters:
        warnings.add(ReleaseWarning.NO_NUMBERS)
    if numbers.volumes and any(chapter.volume is None for chapter in numbers.chapters):
        warnings.add(ReleaseWarning.MIXED_PACK)
    if numbers.ambiguous or tags.ambiguous:
        warnings.add(ReleaseWarning.AMBIGUOUS_NUMBER)
    language = tags.language
    if language is None and _MULTI_WORD.search(tags.text, numbers.title_end):
        language = LANGUAGES["multi"]
    return ParsedRelease(
        title=title,
        volumes=numbers.volumes,
        chapters=numbers.chapters,
        group=tags.group,
        source=tags.source,
        language=language,
        hints=tags.hints,
        file_format=tags.file_format,
        warnings=frozenset(warnings),
    )
