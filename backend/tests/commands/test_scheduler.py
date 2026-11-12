import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from pydantic import NonNegativeFloat, TypeAdapter
from sqlalchemy import select, update

from tests.helpers.clock import FakeClock
from tomarr.commands.purge_http_cache import PURGE_HTTP_CACHE
from tomarr.commands.runner import wait_for_wake
from tomarr.commands.scheduler import CommandScheduler, Schedule
from tomarr.core.database import Database
from tomarr.domain.command import Command, CommandStatus
from tomarr.services.commands import CommandService
from tomarr.services.settings import SettingKey, SettingsRegistry, SettingsService

INTERVAL = 100.0


class Ticks:
    """A wait that ends when the test releases it or the scheduler stops, so a test decides when
    the scheduler ticks again and never really waits."""

    def __init__(self) -> None:
        self._asleep = asyncio.Event()
        self._release = asyncio.Event()

    async def wait(self, stopping: asyncio.Event, delay: float) -> None:
        self._asleep.set()
        waiters = [asyncio.ensure_future(event.wait()) for event in (stopping, self._release)]
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waiters:
                waiter.cancel()
        self._release.clear()

    async def first(self) -> None:
        async with asyncio.timeout(1):
            await self._asleep.wait()

    async def next(self) -> None:
        self._asleep.clear()
        self._release.set()
        async with asyncio.timeout(1):
            await self._asleep.wait()


@pytest.fixture
def clock() -> FakeClock:
    clock = FakeClock()
    clock.now = 1_000.0
    return clock


@pytest.fixture
def settings(database: Database) -> SettingsService:
    return SettingsService(database.session_factory)


@pytest.fixture
def service(database: Database, clock: FakeClock) -> CommandService:
    return CommandService(database.session_factory, on_change=lambda command: None, now=clock)


@pytest.fixture
def interval() -> SettingKey[float]:
    return SettingsRegistry().declare("schedule.test", TypeAdapter(NonNegativeFloat), INTERVAL)


@pytest.fixture
def ticks() -> Ticks:
    return Ticks()


@pytest.fixture
def scheduler(
    service: CommandService,
    settings: SettingsService,
    ticks: Ticks,
    interval: SettingKey[float],
) -> CommandScheduler:
    return CommandScheduler(
        service, settings, [Schedule(PURGE_HTTP_CACHE, interval)], wait=ticks.wait
    )


@asynccontextmanager
async def running(scheduler: CommandScheduler, ticks: Ticks) -> AsyncIterator[None]:
    scheduler.start()
    try:
        await ticks.first()
        yield
    finally:
        await scheduler.stop()


async def commands(database: Database) -> list[Command]:
    async with database.session_factory() as session:
        return list((await session.scalars(select(Command).order_by(Command.id))).all())


async def set_status(database: Database, status: CommandStatus) -> None:
    async with database.session_factory.begin() as session:
        await session.execute(update(Command).values(status=status))


async def test_the_first_tick_queues_one_command(
    scheduler: CommandScheduler, ticks: Ticks, database: Database
) -> None:
    async with running(scheduler, ticks):
        [command] = await commands(database)

    assert (command.type, command.status, command.queued_at) == (
        PURGE_HTTP_CACHE,
        CommandStatus.QUEUED,
        1_000.0,
    )


async def test_it_queues_nothing_while_one_is_queued_or_running(
    scheduler: CommandScheduler, ticks: Ticks, clock: FakeClock, database: Database
) -> None:
    async with running(scheduler, ticks):
        clock.now += 10 * INTERVAL
        await ticks.next()
        await set_status(database, CommandStatus.RUNNING)
        await ticks.next()

        assert len(await commands(database)) == 1


async def test_it_queues_again_once_the_interval_has_passed_since_the_last_was_queued(
    scheduler: CommandScheduler, ticks: Ticks, clock: FakeClock, database: Database
) -> None:
    async with running(scheduler, ticks):
        await set_status(database, CommandStatus.COMPLETED)
        clock.now += INTERVAL - 1
        await ticks.next()
        assert len(await commands(database)) == 1

        clock.now += 1
        await ticks.next()
        assert len(await commands(database)) == 2


async def test_an_interval_of_zero_turns_the_schedule_off(
    scheduler: CommandScheduler,
    ticks: Ticks,
    settings: SettingsService,
    interval: SettingKey[float],
    database: Database,
) -> None:
    await settings.set(interval, 0)

    async with running(scheduler, ticks):
        await ticks.next()

        assert await commands(database) == []


async def test_it_reads_the_interval_from_settings_on_every_tick(
    scheduler: CommandScheduler,
    ticks: Ticks,
    settings: SettingsService,
    interval: SettingKey[float],
    clock: FakeClock,
    database: Database,
) -> None:
    async with running(scheduler, ticks):
        await set_status(database, CommandStatus.COMPLETED)
        clock.now += INTERVAL - 1
        await settings.set(interval, 50)
        await ticks.next()

        assert len(await commands(database)) == 2


async def test_a_new_scheduler_after_a_restart_does_not_queue_early(
    service: CommandService,
    settings: SettingsService,
    interval: SettingKey[float],
    clock: FakeClock,
    database: Database,
) -> None:
    async def run_a_fresh_scheduler() -> None:
        ticks = Ticks()
        schedules = [Schedule(PURGE_HTTP_CACHE, interval)]
        fresh = CommandScheduler(service, settings, schedules, wait=ticks.wait)
        async with running(fresh, ticks):
            pass

    await run_a_fresh_scheduler()
    await set_status(database, CommandStatus.COMPLETED)
    clock.now += INTERVAL - 1
    await run_a_fresh_scheduler()
    assert len(await commands(database)) == 1

    clock.now += 1
    await run_a_fresh_scheduler()
    assert len(await commands(database)) == 2


async def test_a_failing_tick_is_logged_and_the_next_tick_still_queues(
    scheduler: CommandScheduler,
    ticks: Ticks,
    settings: SettingsService,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    database: Database,
) -> None:
    real_get = settings.get
    calls = 0

    async def flaky_get[T](key: SettingKey[T]) -> T:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database is locked")
        return await real_get(key)

    monkeypatch.setattr(settings, "get", flaky_get)

    async with running(scheduler, ticks):
        assert await commands(database) == []
        await ticks.next()

        assert len(await commands(database)) == 1
    [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert record.__dict__["schedule_type"] == PURGE_HTTP_CACHE
    assert record.exc_info is not None


async def test_start_while_running_raises(scheduler: CommandScheduler, ticks: Ticks) -> None:
    async with running(scheduler, ticks):
        with pytest.raises(RuntimeError):
            scheduler.start()


async def test_stop_wakes_a_scheduler_waiting_on_the_real_wait(
    service: CommandService, settings: SettingsService, interval: SettingKey[float]
) -> None:
    idle = asyncio.Event()

    async def wait(stopping: asyncio.Event, delay: float) -> None:
        idle.set()
        await wait_for_wake(stopping, delay)

    scheduler = CommandScheduler(
        service, settings, [Schedule(PURGE_HTTP_CACHE, interval)], wait=wait, tick=3600.0
    )
    scheduler.start()
    async with asyncio.timeout(1):
        await idle.wait()
        await scheduler.stop()


async def test_stop_lets_a_tick_in_progress_finish(
    service: CommandService,
    settings: SettingsService,
    interval: SettingKey[float],
    ticks: Ticks,
    monkeypatch: pytest.MonkeyPatch,
    database: Database,
) -> None:
    real_get = settings.get
    reading = asyncio.Event()
    gate = asyncio.Event()

    async def gated_get[T](key: SettingKey[T]) -> T:
        reading.set()
        await gate.wait()
        return await real_get(key)

    monkeypatch.setattr(settings, "get", gated_get)
    scheduler = CommandScheduler(
        service, settings, [Schedule(PURGE_HTTP_CACHE, interval)], wait=ticks.wait
    )

    scheduler.start()
    async with asyncio.timeout(1):
        await reading.wait()
        stopping = asyncio.create_task(scheduler.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
        gate.set()
        await stopping

    assert len(await commands(database)) == 1
