from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
    """The score cutoffs, from 0 to 100, that turn a title score into a Confidence."""

    high: float
    medium: float

    def __post_init__(self) -> None:
        if not 0 <= self.medium <= self.high <= 100:
            raise ValueError(
                f"thresholds need 0 <= medium <= high <= 100, got high={self.high}, "
                f"medium={self.medium}"
            )
