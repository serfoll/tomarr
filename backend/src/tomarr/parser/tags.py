import re
from dataclasses import dataclass, field

from tomarr.parser.formats import take_extension
from tomarr.parser.markers import read_numbers
from tomarr.parser.release import EditionHint, FileFormat, Source, Unparseable
from tomarr.parser.vocabulary import FORMATS, LANGUAGES, OTHER_FORMATS, names_no_group

# One pass, innermost-first: each branch stops at the next opener of its own kind,
# so a run of unclosed brackets costs a fixed amount per character.
_TAG = re.compile(r"\[[^\[\]]*\]|\([^()]*\)|\{[^{}]*\}")
_ITEM_BREAK = re.compile(r"[,/+]")
_DIGITAL = re.compile(r"digital(?: [sh]d)?")
_COLORED = re.compile(r"colou?red")
_COLORED_COMICS = re.compile(r"colou?red comics")
_MULTI_WORD = re.compile(r"\bMULTi\b")


@dataclass(frozen=True)
class Tags:
    """What the tags of a name say, and the name's text without them.

    A `(...)` or `[...]` tag that holds a Volume or Chapter marker
    (`(v000-v105 & ch0035-1078)`, `[Kagurabachi vol 01-05]`) is not removed:
    its brackets are dropped and its text stays in `text`, so the numbers are
    read with the rest of the name.
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
        """Take in one comma, slash or plus separated item. False when it is none we know."""
        if names_no_group(item):
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
            # A language may be abbreviated with a dot (`[Eng.]`).
            return self._read_language_and_format([w.rstrip(".") for w in item.split()])
        return True

    def _set_source(self, source: Source) -> None:
        if self.source is Source.UNKNOWN:
            self.source = source

    def _read_language_and_format(self, words: list[str]) -> bool:
        if not all(w in LANGUAGES or w in FORMATS or w in OTHER_FORMATS for w in words):
            return False
        for word in words:
            if word in LANGUAGES and self.language is None:
                self.language = LANGUAGES[word]
            elif word in FORMATS and self.file_format is None:
                self.file_format = FORMATS[word]
        return True


def _holds_marker(inner: str) -> bool:
    markers = read_numbers(inner)
    return isinstance(markers, Unparseable) or markers.title_end < len(inner)


def read_tags(name: str) -> Tags:
    """Read group, source, language, hints and file format from the tags of a name.

    A group is the first unrecognized tag among the `[...]` tags that open the
    name, else the last other unrecognized `(...)` or `[...]` tag (`[VIZ Media]
    [LuCaZ]` gives LuCaZ). A `{...}` tag is never a group. A hint or source
    comes from an item standing on its own in a tag, so `(Colored Council)` is a
    group and not a colored edition; only the phrase `Colored Comics` also
    counts in the title. A file extension ending the name (`.zip`) is read as
    the file format and taken off the text.
    """
    name, extension = take_extension(name)
    facts = _Facts(file_format=extension)
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
        # A {...} tag holds extras, an arc or a release version (`{v1.0}`), never
        # the numbers of the release.
        if tag[0][0] != "{" and _holds_marker(inner):
            pieces.append(f" {inner} ")
            continue
        pieces.append(" ")
        items = [item.strip() for item in _ITEM_BREAK.split(inner.lower())]
        if all([facts.read_item(item) for item in items]):
            continue
        if tag[0][0] == "[" and leading:
            leading_group = leading_group or inner.strip()
        # A trailing two-letter tag is a status or source code (`[NR]`, `[BR]`).
        elif tag[0][0] != "{" and len(inner.strip()) > 2:
            trailing_group = inner.strip()
    pieces.append(name[position:])
    text = "".join(pieces)
    if _COLORED_COMICS.search(name.lower()):
        facts.hints.add(EditionHint.COLORED)
    if _MULTI_WORD.search(text) and facts.language is None:
        facts.language = LANGUAGES["multi"]
    return Tags(
        text,
        leading_group or trailing_group,
        facts.source,
        facts.language,
        frozenset(facts.hints),
        facts.file_format,
    )
