from decimal import Decimal

from tomarr.parser.parse import parse_release
from tomarr.parser.release import ParsedRelease


def parsed(name: str) -> ParsedRelease:
    outcome = parse_release(name)
    assert isinstance(outcome, ParsedRelease)
    return outcome


def chapters(*numbers: str) -> frozenset[Decimal]:
    return frozenset(Decimal(number) for number in numbers)
