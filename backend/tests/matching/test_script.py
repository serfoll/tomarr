import pytest

from tomarr.matching.script import comparable, script_groups

JAPANESE = "JAPANESE"


@pytest.mark.parametrize(
    ("name", "groups"),
    [
        ("one piece", {"LATIN"}),
        ("ワンピース", {JAPANESE}),
        ("ひらがな", {JAPANESE}),
        ("鬼滅の刃", {JAPANESE}),
        ("원피스", {"HANGUL"}),
        ("Re:ゼロ", {"LATIN", JAPANESE}),
        ("86", set[str]()),
        ("!?", set[str]()),
        ("", set[str]()),
        ("Берсерк", {"CYRILLIC"}),
    ],
)
def test_script_groups(name: str, groups: set[str]) -> None:
    assert script_groups(name) == frozenset(groups)


def test_comparable_when_groups_intersect() -> None:
    assert comparable(script_groups("one piece"), script_groups("Re:ゼロ"))
    assert comparable(script_groups("ワンピース"), script_groups("Re:ゼロ"))


def test_comparable_when_either_side_has_no_script() -> None:
    assert comparable(script_groups("86"), script_groups("one piece"))
    assert comparable(script_groups("원피스"), script_groups("!?"))
    assert comparable(frozenset(), frozenset())


@pytest.mark.parametrize(
    ("a", "b"),
    [("one piece", "ワンピース"), ("원피스", "ワンピース"), ("Берсерк", "berserk")],
)
def test_not_comparable_without_a_shared_group(a: str, b: str) -> None:
    assert not comparable(script_groups(a), script_groups(b))
