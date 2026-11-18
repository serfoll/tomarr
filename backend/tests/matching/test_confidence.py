import pytest

from tomarr.matching.confidence import Confidence, lower


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (Confidence.HIGH, Confidence.MEDIUM),
        (Confidence.MEDIUM, Confidence.LOW),
        (Confidence.LOW, Confidence.LOW),
    ],
)
def test_lower_drops_a_tier_and_stops_at_low(confidence: Confidence, expected: Confidence) -> None:
    assert lower(confidence) is expected


def test_confidence_values_are_the_tier_names() -> None:
    assert [c.value for c in Confidence] == ["high", "medium", "low"]
