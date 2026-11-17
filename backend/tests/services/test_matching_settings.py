import pytest
from pydantic import ValidationError
from sqlalchemy import text

from tomarr.core.database import Database
from tomarr.matching.confidence import Confidence
from tomarr.matching.matcher import match_title
from tomarr.matching.thresholds import Thresholds
from tomarr.services.matching_settings import HIGH_SCORE, MEDIUM_SCORE, load_thresholds
from tomarr.services.settings import SettingsService, registry


@pytest.fixture
def service(database: Database) -> SettingsService:
    return SettingsService(database.session_factory)


def test_keys_are_declared_with_their_defaults() -> None:
    declared_keys = registry.keys()
    declared = {key.name: key for key in declared_keys}

    assert declared["matching.high_score"] is HIGH_SCORE
    assert declared["matching.medium_score"] is MEDIUM_SCORE
    assert HIGH_SCORE.default == 95
    assert MEDIUM_SCORE.default == 85


async def test_load_thresholds_returns_the_defaults_on_a_fresh_database(
    service: SettingsService,
) -> None:
    assert await load_thresholds(service) == Thresholds(high=95, medium=85)


async def test_load_thresholds_returns_changed_values(service: SettingsService) -> None:
    await service.set(HIGH_SCORE, 90)
    await service.set(MEDIUM_SCORE, 70)

    assert await load_thresholds(service) == Thresholds(high=90, medium=70)


@pytest.mark.parametrize("value", [-1, 100.5])
async def test_value_outside_zero_to_one_hundred_is_refused(
    service: SettingsService, value: float
) -> None:
    with pytest.raises(ValidationError):
        await service.set(HIGH_SCORE, value)
    with pytest.raises(ValidationError):
        await service.set(MEDIUM_SCORE, value)

    assert await load_thresholds(service) == Thresholds(high=95, medium=85)


async def test_stored_medium_above_high_raises(service: SettingsService) -> None:
    await service.set(MEDIUM_SCORE, 97)

    with pytest.raises(ValueError, match="medium"):
        await load_thresholds(service)


async def test_stored_value_outside_the_range_raises(
    database: Database, service: SettingsService
) -> None:
    async with database.session_factory.begin() as session:
        await session.execute(
            text("INSERT INTO setting (key, value) VALUES ('matching.high_score', '150')")
        )

    with pytest.raises(ValidationError):
        await load_thresholds(service)


async def test_lowering_the_high_score_promotes_a_match_to_high(service: SettingsService) -> None:
    # "death note" against "death nota" scores 90 under rapidfuzz's ratio.
    before = match_title("Death Nota", "Death Note", [], await load_thresholds(service))
    await service.set(HIGH_SCORE, 88)
    after = match_title("Death Nota", "Death Note", [], await load_thresholds(service))

    assert before.score == after.score == 90
    assert before.confidence is Confidence.MEDIUM
    assert after.confidence is Confidence.HIGH
