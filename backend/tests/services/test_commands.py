import asyncio
import logging
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPICursor

from tests.helpers.clock import FakeClock
from tomarr.core.database import Database
from tomarr.core.errors import ErrorCode
from tomarr.domain.command import Command, CommandStatus
from tomarr.services.commands import CommandService


@dataclass(frozen=True)
class Change:
    id: int
    status: CommandStatus
    # What another connection reads at the moment on_change runs, so None means not committed.
    stored_status: str | None


class ChangeRecorder:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.changes: list[Change] = []

    def __call__(self, command: Command) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute(
                "SELECT status FROM command WHERE id = ?", (command.id,)
            ).fetchone()
        finally:
            connection.close()
        self.changes.append(Change(command.id, command.status, None if row is None else row[0]))


@pytest.fixture
def clock() -> FakeClock:
    clock = FakeClock()
    clock.now = 1000.0
    return clock


@pytest.fixture
def recorder(db_path: Path) -> ChangeRecorder:
    return ChangeRecorder(db_path)


@pytest.fixture
def service(database: Database, recorder: ChangeRecorder, clock: FakeClock) -> CommandService:
    return CommandService(database.session_factory, on_change=recorder, now=clock)


async def enqueue_at(service: CommandService, clock: FakeClock, at: float, priority: int) -> int:
    clock.now = at
    command = await service.enqueue("Test", priority=priority)
    return command.id


async def test_enqueue_stores_a_queued_row_and_reports_it_after_the_commit(
    service: CommandService, recorder: ChangeRecorder
) -> None:
    command = await service.enqueue("Test", {"series": 7}, priority=2)

    assert command.type == "Test"
    assert command.payload == {"series": 7}
    assert command.priority == 2
    assert command.status is CommandStatus.QUEUED
    assert command.queued_at == 1000.0
    assert command.not_before is None
    assert command.started_at is None
    assert recorder.changes == [Change(command.id, CommandStatus.QUEUED, "queued")]


async def test_enqueue_without_a_payload_stores_an_empty_one(service: CommandService) -> None:
    command = await service.enqueue("Test")

    assert command.payload == {}


async def test_claim_takes_the_highest_priority_then_the_oldest(
    service: CommandService, clock: FakeClock
) -> None:
    low = await enqueue_at(service, clock, 1.0, priority=0)
    high_new = await enqueue_at(service, clock, 3.0, priority=5)
    high_old = await enqueue_at(service, clock, 2.0, priority=5)

    claimed = [await service.claim_next() for _ in range(4)]

    assert [command.id if command else None for command in claimed] == [
        high_old,
        high_new,
        low,
        None,
    ]


async def test_claim_marks_the_command_running_and_reports_it(
    service: CommandService, clock: FakeClock, recorder: ChangeRecorder
) -> None:
    queued = await service.enqueue("Test")
    clock.now = 1005.0

    claimed = await service.claim_next()

    assert claimed is not None
    assert claimed.id == queued.id
    assert claimed.status is CommandStatus.RUNNING
    assert claimed.started_at == 1005.0
    assert recorder.changes[-1] == Change(queued.id, CommandStatus.RUNNING, "running")


async def test_claim_waits_for_not_before(service: CommandService, clock: FakeClock) -> None:
    queued = await service.enqueue("Test", not_before=1010.0)

    clock.now = 1009.9
    early = await service.claim_next()
    clock.now = 1010.0
    due = await service.claim_next()

    assert early is None
    assert due is not None
    assert due.id == queued.id


async def test_two_claims_over_one_row_give_it_to_one_of_them(service: CommandService) -> None:
    queued = await service.enqueue("Test")

    results = await asyncio.gather(service.claim_next(), service.claim_next())

    claimed = [command for command in results if command is not None]
    assert [command.id for command in claimed] == [queued.id]


async def test_complete_stores_the_result_and_end_time(
    service: CommandService, clock: FakeClock, recorder: ChangeRecorder
) -> None:
    queued = await service.enqueue("Test")
    await service.claim_next()
    clock.now = 1020.0

    completed = await service.complete(queued.id, {"deleted": 3})

    assert completed.status is CommandStatus.COMPLETED
    assert completed.result == {"deleted": 3}
    assert completed.ended_at == 1020.0
    assert recorder.changes[-1] == Change(queued.id, CommandStatus.COMPLETED, "completed")


async def test_complete_with_no_result_stores_null(service: CommandService) -> None:
    queued = await service.enqueue("Test")
    await service.claim_next()

    completed = await service.complete(queued.id, None)

    assert completed.result is None


async def test_fail_stores_only_the_error_code(
    service: CommandService, clock: FakeClock, recorder: ChangeRecorder
) -> None:
    queued = await service.enqueue("Test")
    await service.claim_next()
    clock.now = 1020.0

    failed = await service.fail(queued.id, ErrorCode.INTERNAL_ERROR)

    assert failed.status is CommandStatus.FAILED
    assert failed.result == {"error": "internal_error"}
    assert failed.ended_at == 1020.0
    assert recorder.changes[-1] == Change(queued.id, CommandStatus.FAILED, "failed")


@pytest.mark.parametrize(
    ("retry_after", "delay"),
    [(30.0, 30.0), (None, 60.0), (0.0, 5.0), (-3.0, 5.0), (1e9, 3600.0), (math.inf, 3600.0)],
)
async def test_reschedule_queues_the_command_again_after_the_clamped_delay(
    service: CommandService,
    clock: FakeClock,
    recorder: ChangeRecorder,
    retry_after: float | None,
    delay: float,
) -> None:
    queued = await service.enqueue("Test", priority=4)
    clock.now = 1010.0
    await service.claim_next()
    clock.now = 1012.0

    rescheduled = await service.reschedule(queued.id, retry_after, "Prowlarr")

    assert rescheduled.status is CommandStatus.QUEUED
    assert rescheduled.priority == 4
    assert rescheduled.queued_at == 1000.0
    assert rescheduled.started_at is None
    assert rescheduled.waiting_on == "Prowlarr"
    assert rescheduled.not_before == 1012.0 + delay
    assert recorder.changes[-1] == Change(queued.id, CommandStatus.QUEUED, "queued")


async def test_claim_clears_waiting_on(service: CommandService, clock: FakeClock) -> None:
    queued = await service.enqueue("Test")
    await service.claim_next()
    await service.reschedule(queued.id, 10.0, "Prowlarr")
    clock.now += 10.0

    claimed = await service.claim_next()

    assert claimed is not None
    assert claimed.waiting_on is None


async def test_requeue_interrupted_queues_every_running_command(
    service: CommandService, recorder: ChangeRecorder
) -> None:
    first = await service.enqueue("Test")
    second = await service.enqueue("Test")
    done = await service.enqueue("Test")
    waiting = await service.enqueue("Test")
    for _ in range(3):
        await service.claim_next()
    await service.complete(done.id, None)
    recorder.changes.clear()

    count = await service.requeue_interrupted()

    assert count == 2
    assert sorted(recorder.changes, key=lambda change: change.id) == [
        Change(first.id, CommandStatus.QUEUED, "queued"),
        Change(second.id, CommandStatus.QUEUED, "queued"),
    ]
    active = {command.id: command for command in await service.active()}
    assert set(active) == {first.id, second.id, waiting.id}
    assert all(command.status is CommandStatus.QUEUED for command in active.values())
    assert active[first.id].started_at is None


async def test_active_lists_queued_and_running_commands_only(service: CommandService) -> None:
    running = await service.enqueue("Test")
    await service.claim_next()
    completed = await service.enqueue("Test")
    await service.claim_next()
    await service.complete(completed.id, None)
    failed = await service.enqueue("Test")
    await service.claim_next()
    await service.fail(failed.id, ErrorCode.INTERNAL_ERROR)
    queued = await service.enqueue("Test")

    active = await service.active()

    assert {command.id: command.status for command in active} == {
        running.id: CommandStatus.RUNNING,
        queued.id: CommandStatus.QUEUED,
    }


async def test_earliest_not_before_is_the_soonest_future_one_among_queued(
    service: CommandService, clock: FakeClock
) -> None:
    assert await service.earliest_not_before() is None
    await service.enqueue("Test", not_before=1050.0)
    await service.enqueue("Test", not_before=1030.0)
    await service.enqueue("Test", not_before=990.0)
    await service.enqueue("Test")

    assert await service.earliest_not_before() == 1030.0

    clock.now = 1040.0
    assert await service.earliest_not_before() == 1050.0


async def test_earliest_not_before_ignores_running_commands(
    service: CommandService, clock: FakeClock
) -> None:
    await service.enqueue("Test", not_before=1020.0)
    clock.now = 1020.0
    await service.claim_next()
    clock.now = 1000.0

    assert await service.earliest_not_before() is None


async def test_enqueue_if_due_inserts_when_none_was_ever_queued(
    service: CommandService,
) -> None:
    command = await service.enqueue_if_due("Purge", 3600.0)

    assert command is not None
    assert command.type == "Purge"
    assert command.status is CommandStatus.QUEUED


async def test_enqueue_if_due_waits_while_one_is_queued_or_running(
    service: CommandService, clock: FakeClock
) -> None:
    await service.enqueue("Purge")
    clock.now += 7200.0
    while_queued = await service.enqueue_if_due("Purge", 3600.0)
    await service.claim_next()
    while_running = await service.enqueue_if_due("Purge", 3600.0)

    assert while_queued is None
    assert while_running is None


async def test_enqueue_if_due_waits_for_the_interval_since_the_last_one(
    service: CommandService, clock: FakeClock
) -> None:
    last = await service.enqueue("Purge")
    await service.enqueue("Other")
    await service.claim_next()
    await service.complete(last.id, None)

    clock.now = 1000.0 + 3599.0
    early = await service.enqueue_if_due("Purge", 3600.0)
    clock.now = 1000.0 + 3600.0
    due = await service.enqueue_if_due("Purge", 3600.0)

    assert early is None
    assert due is not None
    assert due.queued_at == 4600.0


async def test_enqueue_if_due_with_a_zero_interval_is_off(service: CommandService) -> None:
    assert await service.enqueue_if_due("Purge", 0) is None
    assert await service.active() == []


async def test_a_failing_on_change_is_logged_and_the_change_kept(
    database: Database, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(_command: Command) -> None:
        raise RuntimeError("subscriber gone")

    service = CommandService(database.session_factory, on_change=broken, now=clock)

    with caplog.at_level(logging.ERROR):
        command = await service.enqueue("Test")

    assert [queued.id for queued in await service.active()] == [command.id]
    assert "subscriber gone" in caplog.text


async def test_the_claim_query_uses_the_claim_index(
    service: CommandService, database: Database, db_path: Path
) -> None:
    statements: list[tuple[str, object]] = []

    def capture(
        _connection: Connection,
        _cursor: DBAPICursor,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE command"):
            statements.append((statement, parameters))

    event.listen(database.engine.sync_engine, "before_cursor_execute", capture)
    try:
        await service.claim_next()
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", capture)

    [(statement, parameters)] = statements
    assert isinstance(parameters, tuple)
    connection = sqlite3.connect(db_path)
    try:
        plan = [row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {statement}", parameters)]
    finally:
        connection.close()
    assert any("USING INDEX ix_command_claim" in step for step in plan), plan
    assert not any(step.startswith("SCAN command") for step in plan), plan
    assert not any("TEMP B-TREE" in step for step in plan), plan
