import re

import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from tomarr.api.request_id import RequestIdMiddleware
from tomarr.core.logging import request_id_var

API = "/api/v1"
GENERATED_ID = re.compile(r"[0-9a-f]{32}")


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", f"{API}/system/health", 200),
        ("GET", f"{API}/nowhere", 404),
        ("POST", f"{API}/system/health", 405),
        ("GET", f"{API}/system/status", 401),
        ("POST", f"{API}/auth/setup", 400),
    ],
    ids=["success", "not-found", "method-not-allowed", "not-authenticated", "validation"],
)
def test_every_response_carries_a_generated_request_id(
    client: TestClient, method: str, path: str, status: int
) -> None:
    response = client.request(method, path)

    assert response.status_code == status
    assert GENERATED_ID.fullmatch(response.headers["x-request-id"])


def test_each_request_gets_its_own_id(client: TestClient) -> None:
    first = client.get(f"{API}/system/health").headers["x-request-id"]
    second = client.get(f"{API}/system/health").headers["x-request-id"]

    assert first != second


@pytest.mark.parametrize("inbound", ["proxy-7f3a.9_X", "a", "x" * 64])
def test_a_valid_inbound_id_is_echoed(client: TestClient, inbound: str) -> None:
    response = client.get(f"{API}/system/health", headers={"X-Request-ID": inbound})

    assert response.headers["x-request-id"] == inbound


@pytest.mark.parametrize(
    "inbound",
    ["has space", "line\nbreak", "x" * 65, "abc\r\ninjected: 1", "", "semi;colon"],
    ids=["space", "newline", "65-chars", "crlf", "empty", "semicolon"],
)
def test_an_invalid_inbound_id_is_replaced(client: TestClient, inbound: str) -> None:
    response = client.get(f"{API}/system/health", headers={"X-Request-ID": inbound})

    assert GENERATED_ID.fullmatch(response.headers["x-request-id"])


async def test_the_id_is_in_state_and_the_variable_during_the_request_and_reset_after() -> None:
    seen: dict[str, object] = {}

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen["state"] = scope["state"]["request_id"]
        seen["variable"] = request_id_var.get(None)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "headers": [(b"x-request-id", b"req-1")]}
    await RequestIdMiddleware(app)(scope, receive, send)

    assert seen == {"state": "req-1", "variable": "req-1"}
    assert request_id_var.get(None) is None
    assert (b"x-request-id", b"req-1") in sent[0]["headers"]


async def test_non_http_scopes_pass_through_untouched() -> None:
    passed: list[Scope] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        passed.append(dict(scope))

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    await RequestIdMiddleware(app)({"type": "lifespan"}, receive, send)

    assert passed == [{"type": "lifespan"}]
