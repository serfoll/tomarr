import asyncio
import logging
from http.cookies import Morsel, SimpleCookie
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.params import Depends
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from tomarr.api.auth import require_auth
from tomarr.app import create_app
from tomarr.core.auth import hash_password
from tomarr.core.database import create_database
from tomarr.core.migrations import upgrade_to_head
from tomarr.services.auth import CREDENTIALS, LOCAL_BYPASS, AuthService
from tomarr.services.settings import SettingsService

API = "/api/v1"
GUARDED = f"{API}/system/status"
PUBLIC_PATHS = {
    f"{API}/auth/login",
    f"{API}/auth/logout",
    f"{API}/auth/setup",
    f"{API}/auth/status",
    f"{API}/system/health",
}
USERNAME = "reader"
PASSWORD = "correct horse battery"
LOCAL_PEER = ("192.168.1.5", 50000)
FORWARDING_HEADERS = ("X-Forwarded-For", "Forwarded", "X-Real-IP")


def set_up(
    client: TestClient, username: str = USERNAME, password: str = PASSWORD
) -> httpx2.Response:
    return client.post(f"{API}/auth/setup", data={"username": username, "password": password})


def log_in(
    client: TestClient, username: str = USERNAME, password: str = PASSWORD
) -> httpx2.Response:
    return client.post(f"{API}/auth/login", data={"username": username, "password": password})


def session_cookie(response: httpx2.Response) -> Morsel[str]:
    cookies: SimpleCookie = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    return cookies["tomarr_session"]


def enable_local_bypass(directory: Path) -> None:
    path = directory / "tomarr.db"
    upgrade_to_head(path)

    async def seed() -> None:
        database = create_database(path)
        try:
            await SettingsService(database.session_factory).set(LOCAL_BYPASS, True)
        finally:
            await database.dispose()

    asyncio.run(seed())


def unguarded_paths(app: FastAPI) -> list[str]:
    paths: list[str] = []
    for route in iter_route_contexts(app.routes):
        if route.path is None or not route.path.startswith(API) or route.path in PUBLIC_PATHS:
            continue
        # A route kind without dependencies (a mount, a plain Starlette route) has no guard.
        dependencies: list[Depends] = getattr(route, "dependencies", [])
        if not any(dependency.dependency is require_auth for dependency in dependencies):
            paths.append(route.path)
    return paths


def test_guarded_route_without_credentials_is_401(client: TestClient) -> None:
    assert client.get(GUARDED).status_code == 401


def test_guarded_route_with_a_wrong_key_is_401(client: TestClient) -> None:
    assert client.get(GUARDED, headers={"X-Api-Key": "not-the-key"}).status_code == 401


def test_guarded_route_with_the_right_key_is_200(client: TestClient, api_key: str) -> None:
    assert client.get(GUARDED, headers={"X-Api-Key": api_key}).status_code == 200


def test_the_key_in_the_query_string_is_not_accepted(
    client: TestClient, api_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    # The client logs the full URL, and the key must not reach a failure report.
    caplog.set_level(logging.WARNING, logger="httpx2")

    assert client.get(GUARDED, params={"apikey": api_key}).status_code == 401


def test_a_matching_key_passes_without_reading_the_database(
    client: TestClient, api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unexpected_read(*_args: object) -> bool:
        raise AssertionError("the guard read the database")

    monkeypatch.setattr(AuthService, "verify_session", unexpected_read)
    monkeypatch.setattr(AuthService, "local_bypass_enabled", unexpected_read)

    assert client.get(GUARDED, headers={"X-Api-Key": api_key}).status_code == 200


def test_health_needs_no_credentials(client: TestClient) -> None:
    response = client.get(f"{API}/system/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_lists_health_with_a_response_model_and_no_security() -> None:
    operation = create_app().openapi()["paths"][f"{API}/system/health"]["get"]

    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/Health"}
    assert "security" not in operation


def test_openapi_marks_guarded_routes_with_the_api_key_header_scheme() -> None:
    schema = create_app().openapi()

    assert schema["paths"][GUARDED]["get"]["security"] == [{"APIKeyHeader": []}]
    scheme = schema["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme == {"type": "apiKey", "in": "header", "name": "X-Api-Key"}


def test_auth_status_before_setup_without_credentials(client: TestClient) -> None:
    response = client.get(f"{API}/auth/status")

    assert response.json() == {"setup_required": True, "authenticated": False}


def test_auth_status_is_authenticated_with_the_api_key(client: TestClient, api_key: str) -> None:
    response = client.get(f"{API}/auth/status", headers={"X-Api-Key": api_key})

    assert response.json() == {"setup_required": True, "authenticated": True}


def test_auth_status_after_setup_follows_the_session_cookie(client: TestClient) -> None:
    set_up(client)

    assert client.get(f"{API}/auth/status").json() == {
        "setup_required": False,
        "authenticated": True,
    }

    client.cookies.clear()

    assert client.get(f"{API}/auth/status").json() == {
        "setup_required": False,
        "authenticated": False,
    }


def test_auth_status_is_authenticated_for_a_bypassed_local_client(tmp_path: Path) -> None:
    enable_local_bypass(tmp_path)

    with TestClient(create_app(), client=LOCAL_PEER) as local:
        response = local.get(f"{API}/auth/status")

    assert response.json() == {"setup_required": True, "authenticated": True}


def test_setup_sets_the_session_cookie_and_the_next_guarded_call_passes(
    client: TestClient,
) -> None:
    response = set_up(client)

    assert response.status_code == 204
    assert response.content == b""
    assert "tomarr_session" in response.headers["set-cookie"]
    assert client.get(GUARDED).status_code == 200


def test_a_second_setup_is_409(client: TestClient) -> None:
    set_up(client)

    assert set_up(client, "another", "another password").status_code == 409


@pytest.mark.parametrize(
    ("username", "password"),
    [("u", "12345678"), ("u" * 256, "p" * 256)],
    ids=["shortest", "longest"],
)
def test_setup_accepts_the_boundary_lengths(
    client: TestClient, username: str, password: str
) -> None:
    assert set_up(client, username, password).status_code == 204


@pytest.mark.parametrize(
    ("username", "password"),
    [("", PASSWORD), (USERNAME, "1234567"), ("u" * 257, PASSWORD), (USERNAME, "p" * 257)],
    ids=["empty-username", "short-password", "long-username", "long-password"],
)
def test_setup_rejects_out_of_range_fields_and_stays_open(
    client: TestClient, username: str, password: str
) -> None:
    assert set_up(client, username, password).status_code == 422
    assert client.get(f"{API}/auth/status").json()["setup_required"] is True


def test_login_with_the_right_pair_sets_the_cookie_and_the_guarded_call_passes(
    client: TestClient,
) -> None:
    set_up(client)
    client.cookies.clear()
    assert client.get(GUARDED).status_code == 401

    response = log_in(client)

    assert response.status_code == 204
    assert "tomarr_session" in response.headers["set-cookie"]
    assert client.get(GUARDED).status_code == 200


def test_login_miss_is_401_with_one_body_for_wrong_username_and_wrong_password(
    client: TestClient,
) -> None:
    set_up(client)
    client.cookies.clear()

    wrong_password = log_in(client, USERNAME, "abc")
    wrong_username = log_in(client, "someone-else", PASSWORD)

    assert wrong_password.status_code == 401
    assert wrong_username.status_code == 401
    assert wrong_password.content == wrong_username.content
    assert "set-cookie" not in wrong_password.headers
    assert "set-cookie" not in wrong_username.headers
    assert client.get(GUARDED).status_code == 401


def test_login_before_setup_is_401(client: TestClient) -> None:
    assert log_in(client).status_code == 401


@pytest.mark.parametrize(
    ("username", "password"),
    [("", PASSWORD), (USERNAME, ""), ("u" * 257, PASSWORD), (USERNAME, "p" * 257)],
    ids=["empty-username", "empty-password", "long-username", "long-password"],
)
def test_login_rejects_empty_and_over_long_fields(
    client: TestClient, username: str, password: str
) -> None:
    assert log_in(client, username, password).status_code == 422


def test_logout_clears_the_cookie_and_the_guarded_call_fails(client: TestClient) -> None:
    set_up(client)
    assert client.get(GUARDED).status_code == 200

    response = client.post(f"{API}/auth/logout")

    assert response.status_code == 204
    cleared = session_cookie(response)
    assert cleared.value == ""
    assert cleared["max-age"] == "0"
    assert client.get(GUARDED).status_code == 401


def test_logout_needs_no_session(client: TestClient) -> None:
    assert client.post(f"{API}/auth/logout").status_code == 204


def test_a_garbage_session_cookie_is_401(client: TestClient) -> None:
    set_up(client)
    client.cookies.set("tomarr_session", "garbage")

    assert client.get(GUARDED).status_code == 401


def test_session_cookie_attributes_over_http(client: TestClient) -> None:
    cookie = session_cookie(set_up(client))

    assert cookie["httponly"] is True
    assert cookie["samesite"] == "lax"
    assert cookie["max-age"] == "2592000"
    assert cookie["path"] == "/"
    assert not cookie["secure"]


def test_session_cookie_is_secure_over_https() -> None:
    with TestClient(create_app(), base_url="https://testserver") as secure_client:
        set_up_response = set_up(secure_client)
        logout_response = secure_client.post(f"{API}/auth/logout")

    assert session_cookie(set_up_response)["secure"] is True
    assert session_cookie(logout_response)["secure"] is True


def test_bypass_is_off_by_default() -> None:
    with TestClient(create_app(), client=LOCAL_PEER) as local:
        assert local.get(GUARDED).status_code == 401


@pytest.mark.parametrize("host", ["192.168.1.5", "127.0.0.1", "::1"])
def test_bypass_lets_a_local_client_in_when_enabled(tmp_path: Path, host: str) -> None:
    enable_local_bypass(tmp_path)

    with TestClient(create_app(), client=(host, 50000)) as local:
        assert local.get(GUARDED).status_code == 200


def test_bypass_does_not_let_a_public_client_in(tmp_path: Path) -> None:
    enable_local_bypass(tmp_path)

    with TestClient(create_app(), client=("8.8.8.8", 50000)) as remote:
        assert remote.get(GUARDED).status_code == 401


@pytest.mark.parametrize("header", FORWARDING_HEADERS)
def test_bypass_is_refused_when_a_forwarding_header_is_present(tmp_path: Path, header: str) -> None:
    enable_local_bypass(tmp_path)

    with TestClient(create_app(), client=LOCAL_PEER) as local:
        assert local.get(GUARDED, headers={header: "203.0.113.9"}).status_code == 401


def test_a_password_change_ends_an_existing_session() -> None:
    app = create_app()

    async def change_password() -> None:
        settings = SettingsService(app.state.database.session_factory)
        current = await settings.get(CREDENTIALS)
        assert current is not None
        changed = current.model_copy(update={"password_hash": hash_password("a new password")})
        await settings.set(CREDENTIALS, changed)

    with TestClient(app) as client:
        set_up(client)
        assert client.get(GUARDED).status_code == 200
        assert client.portal is not None

        client.portal.call(change_password)

        assert client.get(GUARDED).status_code == 401


def test_every_api_route_is_guarded_or_public() -> None:
    assert unguarded_paths(create_app()) == []


def test_the_walk_flags_an_unguarded_route() -> None:
    app = create_app()

    @app.get(f"{API}/leak")
    def leak() -> None:
        return None

    assert unguarded_paths(app) == [f"{API}/leak"]
