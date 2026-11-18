from dataclasses import FrozenInstanceError

import pytest

from tomarr.matching.thresholds import Thresholds


def test_thresholds_are_frozen() -> None:
    thresholds = Thresholds(high=95, medium=85)

    with pytest.raises(FrozenInstanceError):
        thresholds.high = 90  # pyright: ignore[reportAttributeAccessIssue]


def test_thresholds_accept_equal_cutoffs_and_the_range_ends() -> None:
    Thresholds(high=100, medium=0)
    Thresholds(high=50, medium=50)


@pytest.mark.parametrize(
    ("high", "medium"),
    [(80, 85), (101, 50), (50, -1), (-1, -2), (101, 101)],
)
def test_thresholds_refuse_medium_above_high_and_values_outside_0_to_100(
    high: float, medium: float
) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        Thresholds(high=high, medium=medium)
