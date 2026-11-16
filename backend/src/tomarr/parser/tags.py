import re
from dataclasses import dataclass, field

from tomarr.parser.markers import read_numbers
from tomarr.parser.release import EditionHint, FileFormat, Source, Unparseable

# One pass, innermost-first: each branch stops at the next opener of its own kind,
# so a run of unclosed brackets costs a fixed amount per character.
_TAG = re.compile(r"\[[^\[\]]*\]|\([^()]*\)|\{[^{}]*\}")
_ITEM_BREAK = re.compile(r"[,/]")
_NUMBERS_ONLY = re.compile(r"[\d\s.\-]*")
_DIGITAL = re.compile(r"digital(?: [sh]d)?")
_COLORED = re.compile(r"colou?red")
_COLORED_COMICS = re.compile(r"colou?red comics")
_MULTI_WORD = re.compile(r"\bMULTi\b")

# ISO 639-2/B codes, because that is how names spell them (`FRE`, `GER`).
_LANGUAGES = {
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
_FORMATS = {format.value: format for format in FileFormat}
# Seen next to a language in a tag, but not a format Tomarr imports.
_OTHER_FORMATS = frozenset({"mobi", "jpg", "azwn"})
# Words that say something about the release but name neither group nor hint.
_NOT_A_GROUP = frozenset(
    {"hq", "manga", "novel", "light novel", "complete", "ongoing", "scanlated", "upscaled"}
)


@dataclass(frozen=True)
class Tags:
    """What the tags of a name say, and the name's text without them.

    A tag that holds a Volume or Chapter marker (`(v000-v105 & ch0035-1078)`,
    `[Kagurabachi vol 01-05]`) is not removed: its brackets are dropped and its
    text stays in `text`, so the numbers are read with the rest of the name.
    """

    text: str
    group: str | None
    source: Source
    language: str | None
    hints: frozenset[EditionHint]
    file_format: FileFormat | None


@dataclass
class _Facts:
    source: Source = Source.UNKNOWN
    language: str | None = None
    file_format: FileFormat | None = None
    hints: set[EditionHint] = field(default_factory=set[EditionHint])

    def read_item(self, item: str) -> bool:
        """Take in one comma or slash separated item. False when it is none we know."""
        if _NUMBERS_ONLY.fullmatch(item) or item in _NOT_A_GROUP:
            return True
        if _DIGITAL.fullmatch(item):
            self._set_source(Source.DIGITAL)
        elif item in {"scan", "scans"}:
            self._set_source(Source.SCAN)
        elif _COLORED.fullmatch(item) or _COLORED_COMICS.search(item):
            self.hints.add(EditionHint.COLORED)
        elif item == "webtoon":
            self.hints.add(EditionHint.WEBTOON)
        else:
            return self._read_language_and_format(item.split())
        return True

    def _set_source(self, source: Source) -> None:
        if self.source is Source.UNKNOWN:
            self.source = source

    def _read_language_and_format(self, words: list[str]) -> bool:
        if not all(w in _LANGUAGES or w in _FORMATS or w in _OTHER_FORMATS for w in words):
            return False
        for word in words:
            if word in _LANGUAGES and self.language is None:
                self.language = _LANGUAGES[word]
            elif word in _FORMATS and self.file_format is None:
                self.file_format = _FORMATS[word]
        return True


def _holds_marker(inner: str) -> bool:
    markers = read_numbers(inner)
    return isinstance(markers, Unparseable) or markers.title_end < len(inner)


def read_tags(name: str) -> Tags:
    """Read group, source, language, hints and file format from the tags of a name.

    A group is the first unrecognized tag among the `[...]` tags that open the
    name, else the last unrecognized `(...)` tag anywhere. A hint or source comes
    from an item standing on its own in a tag, so `(Colored Council)` is a group
    and not a colored edition; only the phrase `Colored Comics` also counts in
    the title.
    """
    facts = _Facts()
    pieces: list[str] = []
    leading_group: str | None = None
    trailing_group: str | None = None
    leading = True
    position = 0
    for tag in _TAG.finditer(name):
        pieces.append(name[position : tag.start()])
        leading = leading and not name[position : tag.start()].strip()
        position = tag.end()
        inner = tag[0][1:-1]
        if _holds_marker(inner):
            pieces.append(f" {inner} ")
            continue
        pieces.append(" ")
        items = [item.strip() for item in _ITEM_BREAK.split(inner.lower())]
        if all([facts.read_item(item) for item in items]):
            continue
        if tag[0][0] == "[" and leading:
            leading_group = leading_group or inner.strip()
        elif tag[0][0] == "(":
            trailing_group = inner.strip()
    pieces.append(name[position:])
    text = "".join(pieces)
    if _COLORED_COMICS.search(name.lower()):
        facts.hints.add(EditionHint.COLORED)
    if _MULTI_WORD.search(text) and facts.language is None:
        facts.language = _LANGUAGES["multi"]
    return Tags(
        text,
        leading_group or trailing_group,
        facts.source,
        facts.language,
        frozenset(facts.hints),
        facts.file_format,
    )
