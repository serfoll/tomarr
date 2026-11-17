import re
import unicodedata

JAPANESE = "JAPANESE"

_JAPANESE_WORDS = frozenset({"HIRAGANA", "KATAKANA", "CJK"})
# The long vowel mark is named "KATAKANA-HIRAGANA PROLONGED SOUND MARK".
_NAME_WORD = re.compile(r"[ -]")


def script_groups(name: str) -> frozenset[str]:
    """Return the script groups of the letters in a normalized name.

    Digits and punctuation count for nothing, so a name of digits only has no group.
    """
    groups: set[str] = set()
    for char in name:
        if not unicodedata.category(char).startswith("L"):
            continue
        word = _NAME_WORD.split(unicodedata.name(char), maxsplit=1)[0]
        groups.add(JAPANESE if word in _JAPANESE_WORDS else word)
    return frozenset(groups)


def comparable(a: frozenset[str], b: frozenset[str]) -> bool:
    """Whether two names may be scored against each other.

    A name with no script is comparable with every name.
    """
    return not a or not b or not a.isdisjoint(b)
