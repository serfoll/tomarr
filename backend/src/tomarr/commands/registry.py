from collections.abc import Awaitable, Callable

type Handler = Callable[[dict[str, object]], Awaitable[dict[str, object] | None]]


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, type: str, handler: Handler) -> None:
        if type in self._handlers:
            raise ValueError(f"A handler for {type!r} is already registered")
        self._handlers[type] = handler

    def get(self, type: str) -> Handler:
        return self._handlers[type]
