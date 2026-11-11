import asyncio
import json
from collections.abc import MutableMapping
from typing import Self

import pytest
from fastapi import FastAPI

from tests.helpers.clock import FakeClock
from tomarr.api import commands
from tomarr.core.broadcaster import Broadcaster
from tomarr.core.database import Database
from tomarr.core.errors import ErrorCode
from tomarr.domain.command import Command
from tomarr.services.commands import CommandService

EVENTS_PATH = "/api/v1/commands/events"
GUARD_SECONDS = 5
type Message = MutableMapping[str, object]


class EventStream:
    """Runs one GET of the events route straight against the ASGI app. A socket would be blocked
    in tests, and an ASGI transport only returns once the response has ended."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._chunks = asyncio.Queue[bytes | None]()
        self._disconnected = asyncio.Event()
        self._buffer = ""
        self._task: asyncio.Task[None] | None = None
        self.status: int | None = None
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> Self:
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, *_exc: object) -> None:
        assert self._task is not None
        self._disconnected.set()
        async with asyncio.timeout(GUARD_SECONDS):
            await self._task

    async def next_event(self) -> tuple[str, object]:
        """The next event as (name, decoded data). Keep-alive comments are skipped."""
        while True:
            while "\n\n" not in self._buffer:
                async with asyncio.timeout(GUARD_SECONDS):
                    chunk = await self._chunks.get()
                assert chunk is not None, "the stream ended before the next event"
                self._buffer += chunk.decode()
            raw, self._buffer = self._buffer.split("\n\n", 1)
            fields = dict(line.split(": ", 1) for line in raw.splitlines() if line[0] != ":")
            if fields:
                return fields["event"], json.loads(fields["data"])

    async def ended(self) -> None:
        assert self._task is not None
        async with asyncio.timeout(GUARD_SECONDS):
            await self._task

    async def disconnect(self) -> None:
        self._disconnected.set()
        await self.ended()

    async def _run(self) -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": EVENTS_PATH,
            "raw_path": EVENTS_PATH.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [],
            "server": ("test", 80),
            "client": ("test", 1),
        }
        requested = False

        async def receive() -> Message:
            nonlocal requested
            if not requested:
                requested = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self._disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.status = int(str(message["status"]))
                raw_headers = message["headers"]
                assert isinstance(raw_headers, list)
                self.headers = {key.decode(): value.decode() for key, value in raw_headers}
            elif message["type"] == "http.response.body":
                body = message["body"]
                assert isinstance(body, bytes)
                if body:
                    self._chunks.put_nowait(body)

        try:
            await self._app(scope, receive, send)
        finally:
            self._chunks.put_nowait(None)


@pytest.fixture
def clock() -> FakeClock:
    clock = FakeClock()
    clock.now = 1000.0
    return clock


@pytest.fixture
def broadcaster() -> Broadcaster[Command]:
    return Broadcaster()


@pytest.fixture
def service(
    database: Database, broadcaster: Broadcaster[Command], clock: FakeClock
) -> CommandService:
    return CommandService(database.session_factory, on_change=broadcaster.publish, now=clock)


@pytest.fixture
def app(service: CommandService, broadcaster: Broadcaster[Command]) -> FastAPI:
    app = FastAPI()
    app.state.commands = service
    app.state.broadcaster = broadcaster
    app.include_router(commands.router, prefix="/api/v1")
    return app


async def run_to_status(service: CommandService, type: str) -> Command:
    """Enqueue a Command and claim it, so it is running. Only one Command is queued at a time in
    these tests, so the claim takes the one just enqueued."""
    await service.enqueue(type)
    claimed = await service.claim_next()
    assert claimed is not None
    return claimed


async def test_the_first_event_is_a_snapshot_of_queued_and_running_commands_only(
    app: FastAPI, service: CommandService, broadcaster: Broadcaster[Command]
) -> None:
    done = await run_to_status(service, "Done")
    await service.complete(done.id, {"deleted": 3})
    broken = await run_to_status(service, "Broken")
    await service.fail(broken.id, ErrorCode.INTERNAL_ERROR)
    running = await run_to_status(service, "Running")
    queued = await service.enqueue("Queued")

    async with EventStream(app) as stream:
        name, data = await stream.next_event()
        broadcaster.close()
        await stream.ended()

    assert name == "snapshot"
    assert isinstance(data, list)
    assert [(item["id"], item["status"]) for item in data] == [
        (running.id, "running"),
        (queued.id, "queued"),
    ]


async def test_a_change_arrives_as_a_command_event_with_the_agreed_fields_only(
    app: FastAPI, service: CommandService
) -> None:
    async with EventStream(app) as stream:
        await stream.next_event()

        command = await service.enqueue("Test", {"secret": "payload"}, priority=2)
        name, data = await stream.next_event()

    assert name == "command"
    assert data == {
        "id": command.id,
        "type": "Test",
        "status": "queued",
        "priority": 2,
        "queued_at": 1000.0,
        "started_at": None,
        "ended_at": None,
        "not_before": None,
        "error": None,
        "waiting_on": None,
    }


async def test_a_completed_event_carries_no_result(app: FastAPI, service: CommandService) -> None:
    running = await run_to_status(service, "Test")

    async with EventStream(app) as stream:
        await stream.next_event()

        await service.complete(running.id, {"deleted": 3})
        name, data = await stream.next_event()

    assert name == "command"
    assert isinstance(data, dict)
    assert data["status"] == "completed"
    assert data["error"] is None
    assert "result" not in data
    assert "payload" not in data


async def test_a_failed_command_event_has_the_error_code(
    app: FastAPI, service: CommandService, clock: FakeClock
) -> None:
    running = await run_to_status(service, "Test")

    async with EventStream(app) as stream:
        await stream.next_event()

        clock.now = 1007.0
        await service.fail(running.id, ErrorCode.INTERNAL_ERROR)
        _, data = await stream.next_event()

    assert isinstance(data, dict)
    assert data["status"] == "failed"
    assert data["error"] == "internal_error"
    assert data["ended_at"] == 1007.0


async def test_a_rescheduled_command_event_names_the_service_and_the_retry_time(
    app: FastAPI, service: CommandService, clock: FakeClock
) -> None:
    running = await run_to_status(service, "Test")

    async with EventStream(app) as stream:
        await stream.next_event()

        await service.reschedule(running.id, 30.0, "Prowlarr")
        _, data = await stream.next_event()

    assert isinstance(data, dict)
    assert data["status"] == "queued"
    assert data["waiting_on"] == "Prowlarr"
    assert data["not_before"] == 1030.0
    assert data["started_at"] is None
    assert data["error"] is None


async def test_a_change_between_subscribing_and_the_snapshot_is_not_lost(
    app: FastAPI, service: CommandService, monkeypatch: pytest.MonkeyPatch
) -> None:
    read_snapshot = service.active
    late_id: list[int] = []

    async def active_then_change() -> list[Command]:
        snapshot = await read_snapshot()
        late_id.append((await service.enqueue("Late")).id)
        return snapshot

    monkeypatch.setattr(service, "active", active_then_change)

    async with EventStream(app) as stream:
        snapshot = await stream.next_event()
        change = await stream.next_event()

    assert snapshot == ("snapshot", [])
    assert change[0] == "command"
    assert isinstance(change[1], dict)
    assert change[1]["id"] == late_id[0]


async def test_the_stream_ends_when_the_broadcaster_closes(
    app: FastAPI, broadcaster: Broadcaster[Command]
) -> None:
    async with EventStream(app) as stream:
        await stream.next_event()

        broadcaster.close()
        await stream.ended()

    assert stream.status == 200


async def test_a_client_that_disconnects_is_unsubscribed(
    app: FastAPI, broadcaster: Broadcaster[Command]
) -> None:
    async with EventStream(app) as stream:
        await stream.next_event()
        assert broadcaster.subscriber_count == 1

        await stream.disconnect()

    assert broadcaster.subscriber_count == 0


def test_the_route_is_an_event_stream_in_openapi_and_describes_the_event(app: FastAPI) -> None:
    schema = app.openapi()

    response = schema["paths"][EVENTS_PATH]["get"]["responses"]["200"]
    assert "text/event-stream" in response["content"]
    event = schema["components"]["schemas"]["CommandStatusEvent"]
    assert set(event["properties"]) == {
        "id",
        "type",
        "status",
        "priority",
        "queued_at",
        "started_at",
        "ended_at",
        "not_before",
        "error",
        "waiting_on",
    }
