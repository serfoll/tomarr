from enum import StrEnum


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_LOWER = {
    Confidence.HIGH: Confidence.MEDIUM,
    Confidence.MEDIUM: Confidence.LOW,
    Confidence.LOW: Confidence.LOW,
}


def lower(confidence: Confidence) -> Confidence:
    """Return the tier below a Confidence. `low` is the floor."""
    return _LOWER[confidence]
