"""The golden corpus: real release names and the outcome written by reading each one.

Each YAML file under `tests/fixtures/releases/` is a list of entries. An entry
has a `name` and either `unparseable: <reason>` (plus `number_reason` where the
normalizer gave one) or the expected Parsed release fields. A field left out
takes its `ParsedRelease` default. Ranges are written `"5"` or `"1-5"`, decimals
as strings, and a chapter range under its volume as `{range: "12-20", volume: "3"}`.
An entry marked `synthetic: true` is written by hand from a naming shape; every
other name is copied character for character from `raw/`.
"""

from collections import Counter
from dataclasses import dataclass, fields
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from tomarr.parser.chapter_number import ChapterNumberReason
from tomarr.parser.parse import parse_release
from tomarr.parser.release import (
    ChapterRange,
    EditionHint,
    FileFormat,
    NumberRange,
    ParsedRelease,
    ParseOutcome,
    ReleaseWarning,
    Source,
    Unparseable,
    UnparseableReason,
)

CORPUS = Path(__file__).parents[1] / "fixtures" / "releases"
MINIMUM_CASES = 300
# A parser that refused every name would return this for each of them.
REJECT_ALL = Unparseable(UnparseableReason.NO_TITLE)

_PARSED_KEYS = frozenset(field.name for field in fields(ParsedRelease))
_ENTRY_KEYS = _PARSED_KEYS | {"name", "synthetic", "unparseable", "number_reason"}


@dataclass(frozen=True)
class Case:
    name: str
    expected: ParseOutcome
    synthetic: bool
    source_file: str


def _number(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"write numbers as integers or strings, not {value!r}")
    return Decimal(str(value))


def _range(value: object) -> NumberRange:
    start, _, end = str(value).partition("-") if isinstance(value, str) else (value, "", "")
    return NumberRange(_number(start), _number(end or start))


def _chapter(value: object) -> ChapterRange:
    if isinstance(value, dict):
        spec: dict[str, object] = {str(key): item for key, item in value.items()}
        numbers = _range(spec["range"])
        return ChapterRange(numbers.start, numbers.end, _number(spec["volume"]))
    numbers = _range(value)
    return ChapterRange(numbers.start, numbers.end)


def _list(entry: dict[str, object], key: str) -> list[object]:
    value = entry.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return list(value)


def _optional_text(entry: dict[str, object], key: str) -> str | None:
    value = entry.get(key)
    return None if value is None else str(value)


def _expected(entry: dict[str, object]) -> ParseOutcome:
    if "unparseable" in entry:
        if entry.keys() & _PARSED_KEYS:
            raise ValueError("an unparseable entry has no parsed fields")
        number_reason = _optional_text(entry, "number_reason")
        return Unparseable(
            UnparseableReason(entry["unparseable"]),
            ChapterNumberReason(number_reason) if number_reason else None,
        )
    file_format = _optional_text(entry, "file_format")
    return ParsedRelease(
        title=str(entry["title"]),
        volumes=tuple(_range(item) for item in _list(entry, "volumes")),
        chapters=tuple(_chapter(item) for item in _list(entry, "chapters")),
        group=_optional_text(entry, "group"),
        source=Source(entry.get("source", Source.UNKNOWN.value)),
        language=_optional_text(entry, "language"),
        hints=frozenset(EditionHint(item) for item in _list(entry, "hints")),
        file_format=FileFormat(file_format) if file_format else None,
        warnings=frozenset(ReleaseWarning(item) for item in _list(entry, "warnings")),
    )


def _load(path: Path) -> list[Case]:
    entries: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{path.name} must hold a list of entries")
    cases: list[Case] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError(f"{path.name}: every entry must be a mapping")
        entry: dict[str, object] = {str(key): value for key, value in raw.items()}
        if unknown := entry.keys() - _ENTRY_KEYS:
            raise ValueError(f"{path.name}: unknown keys {sorted(unknown)} in {entry.get('name')}")
        name = entry["name"]
        if not isinstance(name, str):
            raise ValueError(f"{path.name}: name must be a string, got {name!r}")
        cases.append(Case(name, _expected(entry), entry.get("synthetic") is True, path.name))
    return cases


CASES = [case for path in sorted(CORPUS.glob("*.yaml")) for case in _load(path)]
RAW_NAMES = frozenset(
    line for path in CORPUS.glob("raw/*.txt") for line in path.read_text("utf-8").splitlines()
)


def _difference(expected: ParseOutcome, actual: ParseOutcome) -> str:
    if type(expected) is not type(actual):
        return f"expected {expected}\n  actual {actual}"
    return "\n".join(
        f"{field.name}: expected {getattr(expected, field.name)!r}, "
        f"got {getattr(actual, field.name)!r}"
        for field in fields(expected)
        if getattr(expected, field.name) != getattr(actual, field.name)
    )


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_corpus_case(case: Case) -> None:
    actual = parse_release(case.name)
    if actual != case.expected:
        pytest.fail(f"{case.name}\n{_difference(case.expected, actual)}", pytrace=False)


def test_corpus_has_enough_cases() -> None:
    assert len(CASES) >= MINIMUM_CASES


def test_real_names_are_the_bulk_of_the_corpus() -> None:
    synthetic = [case for case in CASES if case.synthetic]
    assert len(synthetic) * 10 <= len(CASES)


def test_real_names_are_copied_exactly_from_raw() -> None:
    missing = [case.name for case in CASES if not case.synthetic and case.name not in RAW_NAMES]
    assert missing == []


def test_no_two_entries_share_a_name() -> None:
    counts = Counter(case.name for case in CASES)
    assert [name for name, count in counts.items() if count > 1] == []


def test_every_case_fails_for_a_parser_that_rejects_every_name() -> None:
    # A no_title entry would pass against such a parser, so the corpus holds
    # none; the no_title rules are pinned in test_parse.py instead.
    assert [case.name for case in CASES if case.expected == REJECT_ALL] == []
