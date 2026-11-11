import asyncio
import json
from collections.abc import MutableMapping
from typing import Self

from fastapi import FastAPI

EVENTS_PATH = "/api/v1/commands/events"
GUARD_SECONDS = 5
type Message = MutableMapping[str, object]


class EventStream:
    """Runs one GET of the events route straight against the ASGI app. A socket would be blocked
    in tests, and an ASGI transport only returns once the response has ended."""

    def __init__(self, app: FastAPI, api_key: str | None = None) -> None:
        self._app = app
        self._headers = [] if api_key is None else [(b"x-api-key", api_key.encode())]
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
            "headers": self._headers,
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
