from collections.abc import AsyncIterator
from typing import Self

from fastapi import APIRouter, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from tomarr.core.broadcaster import Broadcaster
from tomarr.core.errors import ErrorCode
from tomarr.domain.command import Command, CommandStatus
from tomarr.services.commands import CommandService

router = APIRouter(prefix="/commands")


class CommandStatusEvent(BaseModel):
    """A Command's state without its payload and result, which can hold anything an adapter
    returned. `error` is the one safe slice of the result: a fixed code."""

    id: int
    type: str
    status: CommandStatus
    priority: int
    queued_at: float
    started_at: float | None
    ended_at: float | None
    not_before: float | None
    error: ErrorCode | None
    waiting_on: str | None

    @classmethod
    def from_command(cls, command: Command) -> Self:
        error = None
        if command.status is CommandStatus.FAILED and command.result is not None:
            error = ErrorCode(str(command.result["error"]))
        return cls(
            id=command.id,
            type=command.type,
            status=command.status,
            priority=command.priority,
            queued_at=command.queued_at,
            started_at=command.started_at,
            ended_at=command.ended_at,
            not_before=command.not_before,
            error=error,
            waiting_on=command.waiting_on,
        )


@router.get(
    "/events",
    response_class=EventSourceResponse,
    # FastAPI describes a stream of ServerSentEvent objects without their data. The model here
    # puts CommandStatusEvent in the schema for the generated client.
    responses={
        status.HTTP_200_OK: {
            "model": CommandStatusEvent,
            "description": (
                "Server-Sent Events. A `snapshot` event whose data is a list of every queued and "
                "running Command, then a `command` event per status change."
            ),
        }
    },
)
async def stream_events(request: Request) -> AsyncIterator[ServerSentEvent]:
    service: CommandService = request.app.state.commands
    broadcaster: Broadcaster[Command] = request.app.state.broadcaster
    # Subscribing first means a change that lands while the snapshot is read still arrives as an
    # event. The client may see a Command in both, which is harmless: an event carries full state.
    async with broadcaster.subscribe() as changes:
        active = await service.active()
        yield ServerSentEvent(
            data=[CommandStatusEvent.from_command(command) for command in active],
            event="snapshot",
        )
        async for command in changes:
            yield ServerSentEvent(data=CommandStatusEvent.from_command(command), event="command")
