import asyncio
import math

import pytest

from tests.helpers.clock import FakeClock
from tomarr.core.rate_limit import RateLimiter


def make_limiter(clock: FakeClock, requests: int, interval: float) -> RateLimiter:
    return RateLimiter(requests, interval, clock=clock, sleep=clock.sleep)


async def acquire_and_stamp(limiter: RateLimiter, clock: FakeClock) -> float:
    await limiter.acquire()
    return clock.now


async def test_second_call_starts_one_interval_after_the_first() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, requests=1, interval=10)

    first, second = await asyncio.gather(
        acquire_and_stamp(limiter, clock), acquire_and_stamp(limiter, clock)
    )

    assert (first, second) == (0, 10)


async def test_call_waits_until_the_oldest_leaves_a_window_of_two() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, requests=2, interval=10)

    stamps = await asyncio.gather(*(acquire_and_stamp(limiter, clock) for _ in range(3)))

    assert stamps == [0, 0, 10]


async def test_call_after_a_full_idle_interval_does_not_wait() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, requests=1, interval=10)
    await limiter.acquire()

    clock.now = 10
    async with asyncio.timeout(1):
        await limiter.acquire()

    assert clock.now == 10
    assert clock.sleeping == 0


async def test_callers_are_served_in_the_order_they_asked() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, requests=1, interval=10)
    started: list[int] = []
    stamps: list[float] = []

    async def caller(index: int) -> None:
        await limiter.acquire()
        started.append(index)
        stamps.append(clock.now)

    await asyncio.gather(*(caller(i) for i in range(4)))

    assert started == [0, 1, 2, 3]
    assert stamps == [0, 10, 20, 30]


async def test_late_caller_does_not_jump_a_waiting_one() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, requests=1, interval=10)
    started: list[str] = []

    async def caller(name: str) -> None:
        await limiter.acquire()
        started.append(name)

    await limiter.acquire()
    clock.gate = asyncio.Event()
    waiting = asyncio.create_task(caller("waiting"))
    await clock.sleep_started.wait()
    clock.now = 10
    late = asyncio.create_task(caller("late"))
    for _ in range(3):
        await asyncio.sleep(0)

    clock.gate.set()
    await asyncio.gather(waiting, late)

    assert started == ["waiting", "late"]


async def test_cancelled_waiter_does_not_use_a_slot() -> None:
    clock = FakeClock()
    limiter = make_limiter(clock, requests=1, interval=10)
    await limiter.acquire()
    clock.now = 5
    clock.gate = asyncio.Event()
    cancelled = asyncio.create_task(limiter.acquire())
    await clock.sleep_started.wait()

    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    clock.gate = None
    await limiter.acquire()
    third_start = clock.now
    await limiter.acquire()

    assert (third_start, clock.now) == (10, 20)


@pytest.mark.parametrize(
    ("requests", "interval", "message"),
    [
        (0, 10, "requests must be at least 1"),
        (-1, 10, "requests must be at least 1"),
        (1, 0, "interval must be positive"),
        (1, -5, "interval must be positive"),
        (1, math.nan, "interval must be finite"),
        (1, math.inf, "interval must be finite"),
    ],
)
def test_rejects_a_policy_that_cannot_admit_a_call(
    requests: int, interval: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RateLimiter(requests, interval, clock=FakeClock(), sleep=FakeClock().sleep)
