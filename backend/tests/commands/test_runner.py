import asyncio
import datetime
import logging
import math
from collections.abc import AsyncIterator

import pytest

from tests.helpers.clock import FakeClock
from tomarr.commands.registry import CommandRegistry, Handler
from tomarr.commands.runner import ERROR_BACKOFF, MAX_WAIT, CommandRunner, wait_for_wake
from tomarr.core.database import Database
from tomarr.core.errors import DomainError, ErrorCode, RateLimited
from tomarr.domain.command import Command, CommandStatus
from tomarr.services.commands import CommandService

GUARD = 2.0


class FakeWait:
    """Waits only for a wake signal and records each timeout it was given, so a test sees how
    long a worker would have slept without ever sleeping."""

    def __init__(self) -> None:
        self.timeouts: list[float] = []
        self._waiting = asyncio.Event()

    async def __call__(self, event: asyncio.Event, delay: float) -> None:
        self.timeouts.append(delay)
        self._waiting.set()
        await event.wait()

    async def idle(self) -> None:
        """Returns once a worker has nothing to do and has started waiting."""
        async with asyncio.timeout(GUARD):
            await self._waiting.wait()
        self._waiting.clear()


class Calls:
    def __init__(self, handler: Handler) -> None:
        self.payloads: list[dict[str, object]] = []
        self._handler = handler

    async def __call__(self, payload: dict[str, object]) -> dict[str, object] | None:
        self.payloads.append(payload)
        return await self._handler(payload)


class Boom(DomainError):
    code = ErrorCode.HTTP_ERROR


@pytest.fixture
def clock() -> FakeClock:
    clock = FakeClock()
    clock.now = 1000.0
    return clock


@pytest.fixture
def service(database: Database, clock: FakeClock) -> CommandService:
    return CommandService(database.session_factory, on_change=lambda command: None, now=clock)


@pytest.fixture
def registry() -> CommandRegistry:
    return CommandRegistry()


@pytest.fixture
def wait() -> FakeWait:
    return FakeWait()


@pytest.fixture
async def runner(
    service: CommandService, registry: CommandRegistry, clock: FakeClock, wait: FakeWait
) -> AsyncIterator[CommandRunner]:
    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=wait)
    yield runner
    async with asyncio.timeout(GUARD):
        await runner.stop()


async def stored(database: Database, id: int) -> Command:
    async with database.session_factory() as session:
        command = await session.get(Command, id)
    assert command is not None
    return command


def register(registry: CommandRegistry, handler: Handler) -> Calls:
    calls = Calls(handler)
    registry.register("Test", calls)
    return calls


async def test_a_command_runs_and_records_its_result(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        return {"seen": payload["series"]}

    calls = register(registry, handler)
    command = await service.enqueue("Test", {"series": 7})

    runner.start()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.COMPLETED
    assert row.result == {"seen": 7}
    assert calls.payloads == [{"series": 7}]


async def test_a_raising_handler_fails_with_only_the_internal_error_code(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        raise RuntimeError("GET https://prowlarr.local/api?apikey=secret failed")

    register(registry, handler)
    command = await service.enqueue("Test")

    runner.start()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "internal_error"}
    [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert getattr(record, "command_id", None) == command.id


async def test_a_domain_error_stores_its_own_code(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        raise Boom("upstream answered 502")

    register(registry, handler)
    command = await service.enqueue("Test")

    runner.start()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "http_error"}


async def test_an_unknown_type_fails_with_internal_error(
    runner: CommandRunner, service: CommandService, database: Database, wait: FakeWait
) -> None:
    command = await service.enqueue("Missing")

    runner.start()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "internal_error"}


async def test_a_rate_limited_command_is_rescheduled_and_not_retried_before_it_is_due(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    clock: FakeClock,
    wait: FakeWait,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        if len(calls.payloads) == 1:
            raise RateLimited("Prowlarr", 30.0)
        return {"ok": True}

    calls = register(registry, handler)
    command = await service.enqueue("Test")

    runner.start()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.QUEUED
    assert row.waiting_on == "Prowlarr"
    assert row.not_before == 1030.0
    assert len(calls.payloads) == 1
    assert wait.timeouts == [30.0]

    clock.now = 1029.5
    runner.wake()
    await wait.idle()

    assert len(calls.payloads) == 1
    assert wait.timeouts[-1] == pytest.approx(0.5)

    clock.now = 1030.0
    runner.wake()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.COMPLETED
    assert row.result == {"ok": True}
    assert len(calls.payloads) == 2


async def test_two_workers_never_run_the_same_command_twice(
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    clock: FakeClock,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        # Yield so the other worker gets a turn while this Command is running.
        await asyncio.sleep(0)
        return None

    calls = register(registry, handler)
    ids = [(await service.enqueue("Test", {"n": n})).id for n in range(10)]
    waiting = 0
    both_idle = asyncio.Event()

    async def wait(event: asyncio.Event, delay: float) -> None:
        nonlocal waiting
        waiting += 1
        if waiting == 2:
            both_idle.set()
        await event.wait()

    runner = CommandRunner(service, registry, workers=2, clock=clock, wait=wait)
    runner.start()
    try:
        async with asyncio.timeout(GUARD):
            await both_idle.wait()
    finally:
        async with asyncio.timeout(GUARD):
            await runner.stop()

    assert sorted(p["n"] for p in calls.payloads if isinstance(p["n"], int)) == list(range(10))
    for id in ids:
        assert (await stored(database, id)).status is CommandStatus.COMPLETED


async def test_a_wake_signal_starts_a_waiting_worker(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        return None

    calls = register(registry, handler)
    runner.start()
    await wait.idle()
    assert wait.timeouts == [MAX_WAIT]

    command = await service.enqueue("Test")
    runner.wake()
    await wait.idle()

    assert len(calls.payloads) == 1
    assert (await stored(database, command.id)).status is CommandStatus.COMPLETED


@pytest.mark.parametrize(("delay", "expected"), [(12.0, 12.0), (100.0, MAX_WAIT)])
async def test_with_nothing_due_the_wait_lasts_until_the_earliest_not_before_capped(
    runner: CommandRunner,
    service: CommandService,
    clock: FakeClock,
    wait: FakeWait,
    delay: float,
    expected: float,
) -> None:
    await service.enqueue("Test", not_before=clock.now + delay)

    runner.start()
    await wait.idle()

    assert wait.timeouts == [expected]


async def test_stop_cancels_a_running_handler_and_leaves_the_row_running(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
) -> None:
    started = asyncio.Event()
    cancelled = False

    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        nonlocal cancelled
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled = True
            raise
        return None

    register(registry, handler)
    command = await service.enqueue("Test")

    runner.start()
    async with asyncio.timeout(GUARD):
        await started.wait()
        await runner.stop()

    assert cancelled
    row = await stored(database, command.id)
    assert row.status is CommandStatus.RUNNING
    assert row.result is None


async def test_wait_for_wake_returns_on_the_signal_or_the_timeout() -> None:
    event = asyncio.Event()
    async with asyncio.timeout(GUARD):
        await wait_for_wake(event, 0.0)
        event.set()
        await wait_for_wake(event, MAX_WAIT)


class FlakyService(CommandService):
    """Fails its first claim, the way a locked database would."""

    claims = 0

    async def claim_next(self) -> Command | None:
        self.claims += 1
        if self.claims == 1:
            raise RuntimeError("database is locked")
        return await super().claim_next()


async def test_a_failing_service_call_is_logged_and_the_worker_keeps_going(
    database: Database,
    registry: CommandRegistry,
    clock: FakeClock,
    wait: FakeWait,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        return None

    register(registry, handler)
    service = FlakyService(database.session_factory, on_change=lambda command: None, now=clock)
    command = await service.enqueue("Test")
    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=wait)

    runner.start()
    try:
        await wait.idle()
        assert wait.timeouts == [ERROR_BACKOFF]
        assert [r.getMessage() for r in caplog.records] == ["Command worker failed"]

        runner.wake()
        await wait.idle()
    finally:
        async with asyncio.timeout(GUARD):
            await runner.stop()

    assert (await stored(database, command.id)).status is CommandStatus.COMPLETED


async def test_a_result_that_cannot_be_stored_fails_and_the_pool_keeps_working(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        if payload.get("bad"):
            return {"when": datetime.datetime.now(datetime.UTC)}
        return {"ok": True}

    register(registry, handler)
    bad = await service.enqueue("Test", {"bad": True})

    runner.start()
    await wait.idle()

    row = await stored(database, bad.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "internal_error"}

    good = await service.enqueue("Test")
    runner.wake()
    await wait.idle()

    assert (await stored(database, good.id)).status is CommandStatus.COMPLETED


async def test_stop_logs_a_worker_that_died_with_an_error(
    service: CommandService,
    registry: CommandRegistry,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reached = asyncio.Event()

    async def broken_wait(event: asyncio.Event, delay: float) -> None:
        reached.set()
        raise RuntimeError("wait broke")

    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=broken_wait)
    runner.start()
    async with asyncio.timeout(GUARD):
        await reached.wait()
        await runner.stop()

    [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert record.getMessage() == "Command worker stopped with an error"
    assert record.exc_info is not None


def with_text_code() -> DomainError:
    # An instance attribute, since a subclass here would break the test that every DomainError
    # subclass has a valid code.
    error = DomainError("x")
    error.code = "boom"  # pyright: ignore[reportAttributeAccessIssue]
    return error


@pytest.mark.parametrize("error", [DomainError("x"), with_text_code()], ids=["none", "text"])
async def test_a_domain_error_without_a_valid_code_fails_with_internal_error(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
    error: DomainError,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        raise error

    register(registry, handler)
    command = await service.enqueue("Test")

    runner.start()
    await wait.idle()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "internal_error"}


class Fatal(BaseException):
    pass


async def cancel_itself(payload: dict[str, object]) -> dict[str, object] | None:
    future = asyncio.get_running_loop().create_future()
    future.cancel()
    await future
    return None


async def raise_a_base_exception(payload: dict[str, object]) -> dict[str, object] | None:
    raise Fatal


@pytest.mark.parametrize("handler", [cancel_itself, raise_a_base_exception])
async def test_a_handler_ending_without_an_exception_fails_and_the_worker_keeps_going(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
    handler: Handler,
) -> None:
    async def ok(payload: dict[str, object]) -> dict[str, object] | None:
        return {"ok": True}

    registry.register("Odd", handler)
    register(registry, ok)
    odd = await service.enqueue("Odd")

    runner.start()
    await wait.idle()

    row = await stored(database, odd.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "internal_error"}

    good = await service.enqueue("Test")
    runner.wake()
    await wait.idle()

    assert (await stored(database, good.id)).status is CommandStatus.COMPLETED


class FailFailsOnce(CommandService):
    """Fails its first fail, the way a locked database would."""

    fails = 0

    async def fail(self, id: int, error: ErrorCode) -> Command:
        self.fails += 1
        if self.fails == 1:
            raise RuntimeError("database is locked")
        return await super().fail(id, error)


async def test_a_command_whose_outcome_cannot_be_stored_is_failed_instead_of_left_running(
    database: Database,
    registry: CommandRegistry,
    clock: FakeClock,
    wait: FakeWait,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        raise RuntimeError("upstream broke")

    register(registry, handler)
    service = FailFailsOnce(database.session_factory, on_change=lambda command: None, now=clock)
    command = await service.enqueue("Test")
    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=wait)

    runner.start()
    try:
        await wait.idle()
    finally:
        async with asyncio.timeout(GUARD):
            await runner.stop()

    row = await stored(database, command.id)
    assert row.status is CommandStatus.FAILED
    assert row.result == {"error": "internal_error"}
    assert wait.timeouts == [ERROR_BACKOFF]
    [worker_failed] = [r for r in caplog.records if r.getMessage() == "Command worker failed"]
    assert getattr(worker_failed, "command_id", None) == command.id


class FailAlwaysFails(CommandService):
    async def fail(self, id: int, error: ErrorCode) -> Command:
        raise RuntimeError("database is locked")


async def test_a_failed_failure_record_is_logged_and_the_worker_keeps_going(
    database: Database,
    registry: CommandRegistry,
    clock: FakeClock,
    wait: FakeWait,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        if payload.get("bad"):
            raise RuntimeError("upstream broke")
        return None

    register(registry, handler)
    service = FailAlwaysFails(database.session_factory, on_change=lambda command: None, now=clock)
    stuck = await service.enqueue("Test", {"bad": True})
    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=wait)

    runner.start()
    try:
        await wait.idle()
        good = await service.enqueue("Test")
        runner.wake()
        await wait.idle()
    finally:
        async with asyncio.timeout(GUARD):
            await runner.stop()

    assert (await stored(database, good.id)).status is CommandStatus.COMPLETED
    [record] = [r for r in caplog.records if r.getMessage() == "Command could not be failed"]
    assert getattr(record, "command_id", None) == stuck.id


async def test_a_nan_retry_after_waits_the_default_delay(
    runner: CommandRunner,
    service: CommandService,
    registry: CommandRegistry,
    database: Database,
    wait: FakeWait,
) -> None:
    async def handler(payload: dict[str, object]) -> dict[str, object] | None:
        raise RateLimited("Prowlarr", math.nan)

    calls = register(registry, handler)
    command = await service.enqueue("Test")

    runner.start()
    await wait.idle()

    assert len(calls.payloads) == 1
    assert (await stored(database, command.id)).not_before == 1060.0
    assert wait.timeouts == [MAX_WAIT]


async def test_start_while_running_raises(runner: CommandRunner) -> None:
    runner.start()

    with pytest.raises(RuntimeError):
        runner.start()


async def test_stop_wakes_a_worker_waiting_on_the_real_wait(
    service: CommandService, registry: CommandRegistry, clock: FakeClock
) -> None:
    idle = asyncio.Event()

    async def wait(event: asyncio.Event, delay: float) -> None:
        idle.set()
        await wait_for_wake(event, delay)

    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=wait)
    runner.start()
    async with asyncio.timeout(GUARD):
        await idle.wait()
        await runner.stop()


class GatedClaims(CommandService):
    """Holds each claim until the test opens the gate, and records whether one was cancelled."""

    def __init__(self, database: Database, clock: FakeClock) -> None:
        super().__init__(database.session_factory, on_change=lambda command: None, now=clock)
        self.claiming = asyncio.Event()
        self.gate = asyncio.Event()
        self.cancelled = False

    async def claim_next(self) -> Command | None:
        self.claiming.set()
        try:
            await self.gate.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return await super().claim_next()


async def test_stop_lets_a_service_call_finish_and_leaves_a_command_claimed_meanwhile_running(
    database: Database, registry: CommandRegistry, clock: FakeClock, wait: FakeWait
) -> None:
    calls = register(registry, cancel_itself)
    service = GatedClaims(database, clock)
    command = await service.enqueue("Test")
    runner = CommandRunner(service, registry, workers=1, clock=clock, wait=wait)

    runner.start()
    async with asyncio.timeout(GUARD):
        await service.claiming.wait()
        stopping = asyncio.create_task(runner.stop())
        await asyncio.sleep(0)
        assert not stopping.done()
        service.gate.set()
        await stopping

    assert not service.cancelled
    assert calls.payloads == []
    row = await stored(database, command.id)
    assert row.status is CommandStatus.RUNNING
    assert row.result is None
