import re
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tomarr.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
# The inbound ID is client input that lands on every log line, so a value that could break the
# line or forge a field is replaced, never cleaned up.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)


def _request_id(scope: Scope) -> str:
    inbound = Headers(scope=scope).get(REQUEST_ID_HEADER)
    if inbound is not None and _VALID_REQUEST_ID.fullmatch(inbound):
        return inbound
    return uuid4().hex
