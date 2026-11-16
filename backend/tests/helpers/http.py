import httpx2

from tests.helpers.clock import FakeClock
from tomarr.core.database import Database
from tomarr.core.http import HttpClientFactory


def make_factory(
    database: Database,
    clock: FakeClock,
    wall: FakeClock,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> HttpClientFactory:
    return HttpClientFactory(
        database.session_factory, transport=transport, clock=clock, sleep=clock.sleep, now=wall
    )
