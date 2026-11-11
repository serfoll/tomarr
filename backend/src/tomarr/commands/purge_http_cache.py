from pydantic import NonNegativeFloat, TypeAdapter

from tomarr.commands.registry import Handler
from tomarr.core.response_cache import ResponseCache
from tomarr.services.settings import registry

PURGE_HTTP_CACHE_INTERVAL = registry.declare(
    "schedule.purge_http_cache", TypeAdapter(NonNegativeFloat), 86_400.0
)


def make_purge_handler(cache: ResponseCache) -> Handler:
    async def purge(payload: dict[str, object]) -> dict[str, object] | None:
        return {"deleted": await cache.purge_expired()}

    return purge
