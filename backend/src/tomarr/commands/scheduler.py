import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from tomarr.services.commands import CommandService
from tomarr.services.settings import SettingKey, SettingsService


@dataclass(frozen=True)
class Schedule:
    type: str
    setting_key: SettingKey[float]


class CommandScheduler:
    """Queues each scheduled Command type when its interval is due. All recurrence state lives in
    the command table, so a restart neither queues early nor forgets."""

    def __init__(
        self,
        service: CommandService,
        settings: SettingsService,
        schedules: Sequence[Schedule],
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
        tick: float = 10.0,
    ) -> None:
        self._service = service
        self._settings = settings
        self._schedules = schedules
        self._sleep = sleep
        self._tick = tick
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while True:
            for schedule in self._schedules:
                interval = await self._settings.get(schedule.setting_key)
                await self._service.enqueue_if_due(schedule.type, interval)
            await self._sleep(self._tick)
