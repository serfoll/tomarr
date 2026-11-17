from typing import Annotated

from pydantic import Field, TypeAdapter

from tomarr.matching.thresholds import Thresholds
from tomarr.services.settings import SettingsService, registry

_SCORE = TypeAdapter(Annotated[float, Field(ge=0, le=100)])

# A judgment, not a measured value.
HIGH_SCORE = registry.declare("matching.high_score", _SCORE, 95)
MEDIUM_SCORE = registry.declare("matching.medium_score", _SCORE, 85)


async def load_thresholds(settings: SettingsService) -> Thresholds:
    return Thresholds(high=await settings.get(HIGH_SCORE), medium=await settings.get(MEDIUM_SCORE))
