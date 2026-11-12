import asyncio
from http.cookies import Morsel, SimpleCookie
from pathlib import Path

import httpx2
import pytest
from fastapi import Depends, FastAPI, params
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from tests.helpers.event_stream import EVENTS_PATH
from tomarr.api.auth import require_auth
from tomarr.app import create_app
from tomarr.core.auth import hash_password
from tomarr.core.database import create_database
from tomarr.core.migrations import upgrade_to_head
from tomarr.services.auth import CREDENTIALS, LOCAL_BYPASS, MIN_PASSWORD_LENGTH, AuthService
from tomarr.services.settings import SettingsService

API = "/api/v1"
GUARDED = f"{API}/system/status"
PUBLIC_ROUTES = {
    ("POST", f"{API}/auth/login"),
    ("POST", f"{API}/auth/logout"),
    ("POST", f"{API}/auth/setup"),
    ("GET", f"{API}/auth/status"),
    ("GET", f"{API}/system/health"),
    ("HEAD", f"{API}/system/health"),
}
USERNAME = "reader"
PASSWORD = "correct horse battery"
LOCAL_PEER = ("192.168.1.5", 50000)
PROXY_HEADERS = (
    "X-Forwarded-For",
    "X-Forwarded-Host",
    "X-Forwarded-Proto",
    "Forwarded",
    "Forwarded-Host",
    "X-Real-IP",
    "CF-Connecting-IP",
    "True-Client-IP",
    "X-Client-IP",
    "Via",
)


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


def sets_session_cookie(response: httpx2.Response) -> bool:
    # A bare `in` on the header would print the cookie value in a failure report.
    return any(
        header.startswith("tomarr_session=") for header in response.headers.get_list("set-cookie")
    )


def error_code(response: httpx2.Response) -> str:
    body = response.json()
    assert set(body) == {"code", "message", "request_id"}
    return body["code"]


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


def form_field_limits(schema: str, field: str) -> tuple[int, int]:
    properties = create_app().openapi()["components"]["schemas"][schema]["properties"][field]
    return properties["minLength"], properties["maxLength"]


def unguarded_paths(app: FastAPI) -> list[str]:
    paths: list[str] = []
    for route in iter_route_contexts(app.routes):
        if route.path is None or not route.path.startswith(API):
            continue
        methods: set[str] = getattr(route, "methods", None) or set()
        if methods and all((method, route.path) in PUBLIC_ROUTES for method in methods):
            continue
        # A route kind without dependencies (a mount, a plain Starlette route) has no guard.
        dependencies: list[params.Depends] = getattr(route, "dependencies", [])
        if not any(dependency.dependency is require_auth for dependency in dependencies):
            paths.append(route.path)
    return paths


def test_guarded_route_without_credentials_is_401_not_authenticated(client: TestClient) -> None:
    response = client.get(GUARDED)

    assert response.status_code == 401
    assert error_code(response) == "not_authenticated"
    assert response.headers["www-authenticate"] == "APIKey"


def test_guarded_route_with_a_wrong_key_is_401(client: TestClient) -> None:
    assert client.get(GUARDED, headers={"X-Api-Key": "not-the-key"}).status_code == 401


def test_the_key_in_the_query_string_is_not_accepted(client: TestClient, api_key: str) -> None:
    response = client.get(GUARDED, params={"apikey": api_key})

    assert response.status_code == 401


def test_a_matching_key_passes_without_reading_the_database(
    client: TestClient, api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unexpected_read(*_args: object) -> bool:
        raise AssertionError("the guard read the database")

    monkeypatch.setattr(AuthService, "verify_session", unexpected_read)
    monkeypatch.setattr(AuthService, "local_bypass_enabled", unexpected_read)

    response = client.get(GUARDED, headers={"X-Api-Key": api_key})

    assert response.status_code == 200


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


def test_openapi_auth_status_is_public_and_guarded_routes_keep_the_security_entry() -> None:
    paths = create_app().openapi()["paths"]

    assert "security" not in paths[f"{API}/auth/status"]["get"]
    assert paths[GUARDED]["get"]["security"] == [{"APIKeyHeader": []}]


ERROR_RESPONSE_REF = {"$ref": "#/components/schemas/ErrorResponse"}


def test_openapi_declares_401_on_guarded_operations() -> None:
    responses = create_app().openapi()["paths"][GUARDED]["get"]["responses"]

    assert responses["401"]["description"]
    assert responses["401"]["content"]["application/json"]["schema"] == ERROR_RESPONSE_REF


def test_openapi_declares_401_on_login_and_409_on_setup() -> None:
    paths = create_app().openapi()["paths"]
    login = paths[f"{API}/auth/login"]["post"]["responses"]
    setup = paths[f"{API}/auth/setup"]["post"]["responses"]

    assert login["401"]["description"]
    assert login["401"]["content"]["application/json"]["schema"] == ERROR_RESPONSE_REF
    assert setup["409"]["description"]
    assert setup["409"]["content"]["application/json"]["schema"] == ERROR_RESPONSE_REF


@pytest.mark.parametrize("path", [f"{API}/system/health", f"{API}/auth/status"])
def test_openapi_does_not_declare_401_on_public_reads(path: str) -> None:
    assert "401" not in create_app().openapi()["paths"][path]["get"]["responses"]


def test_openapi_describes_the_error_response_shape() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    assert schemas["ErrorResponse"]["properties"] == {
        "code": {"$ref": "#/components/schemas/ErrorCode"},
        "message": {"type": "string", "title": "Message"},
        "request_id": {"type": "string", "title": "Request Id"},
    }
    assert schemas["ErrorResponse"]["required"] == ["code", "message", "request_id"]
    assert "ErrorDetail" not in schemas


def test_openapi_keeps_the_success_codes_of_login_setup_and_status() -> None:
    paths = create_app().openapi()["paths"]

    assert "204" in paths[f"{API}/auth/login"]["post"]["responses"]
    assert "204" in paths[f"{API}/auth/setup"]["post"]["responses"]
    assert "200" in paths[f"{API}/auth/status"]["get"]["responses"]


def test_openapi_declares_the_form_field_limits() -> None:
    # FastAPI answers an empty form value as a missing field, so the minimum of 1 only shows here.
    assert form_field_limits("Body_login_api_v1_auth_login_post", "username") == (1, 256)
    assert form_field_limits("Body_login_api_v1_auth_login_post", "password") == (1, 256)
    assert form_field_limits("Body_setup_api_v1_auth_setup_post", "username") == (1, 256)
    assert form_field_limits("Body_setup_api_v1_auth_setup_post", "password") == (8, 256)


def test_openapi_auth_status_lists_the_password_minimum_as_a_required_integer() -> None:
    schema = create_app().openapi()["components"]["schemas"]["AuthStatus"]

    assert schema["properties"]["password_min_length"]["type"] == "integer"
    assert "password_min_length" in schema["required"]


def test_auth_status_password_minimum_is_the_one_the_setup_form_enforces(
    client: TestClient,
) -> None:
    minimum, _ = form_field_limits("Body_setup_api_v1_auth_setup_post", "password")

    assert client.get(f"{API}/auth/status").json()["password_min_length"] == minimum


def test_auth_status_before_setup_without_credentials(client: TestClient) -> None:
    response = client.get(f"{API}/auth/status")

    assert response.json() == {
        "setup_required": True,
        "authenticated": False,
        "password_min_length": MIN_PASSWORD_LENGTH,
    }


def test_auth_status_is_authenticated_with_the_api_key(client: TestClient, api_key: str) -> None:
    response = client.get(f"{API}/auth/status", headers={"X-Api-Key": api_key})

    assert response.json() == {
        "setup_required": True,
        "authenticated": True,
        "password_min_length": MIN_PASSWORD_LENGTH,
    }


def test_auth_status_after_setup_follows_the_session_cookie(client: TestClient) -> None:
    set_up(client)

    assert client.get(f"{API}/auth/status").json() == {
        "setup_required": False,
        "authenticated": True,
        "password_min_length": MIN_PASSWORD_LENGTH,
    }

    client.cookies.clear()

    assert client.get(f"{API}/auth/status").json() == {
        "setup_required": False,
        "authenticated": False,
        "password_min_length": MIN_PASSWORD_LENGTH,
    }


def test_auth_status_is_authenticated_for_a_bypassed_local_client(tmp_path: Path) -> None:
    enable_local_bypass(tmp_path)

    with TestClient(create_app(), client=LOCAL_PEER) as local:
        response = local.get(f"{API}/auth/status")

    assert response.json() == {
        "setup_required": True,
        "authenticated": True,
        "password_min_length": MIN_PASSWORD_LENGTH,
    }


def test_setup_sets_the_session_cookie_and_the_next_guarded_call_passes(
    client: TestClient,
) -> None:
    response = set_up(client)

    assert response.status_code == 204
    assert response.content == b""
    assert sets_session_cookie(response)
    assert client.get(GUARDED).status_code == 200


def test_a_second_setup_is_409_setup_already_done(client: TestClient) -> None:
    set_up(client)

    response = set_up(client, "another", "another password")

    assert response.status_code == 409
    assert error_code(response) == "setup_already_done"


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
    [
        ("", PASSWORD),
        (USERNAME, "1234567"),
        ("u" * 257, PASSWORD),
        (USERNAME, "p" * 257),
        ("   ", PASSWORD),
        (USERNAME, " " * 8),
        (USERNAME, "\t \n" * 3),
    ],
    ids=[
        "empty-username",
        "short-password",
        "long-username",
        "long-password",
        "blank-username",
        "blank-password",
        "whitespace-password",
    ],
)
def test_setup_rejects_out_of_range_fields_and_stays_open(
    client: TestClient, username: str, password: str
) -> None:
    response = set_up(client, username, password)

    assert response.status_code == 400
    assert error_code(response) == "validation_failed"
    assert client.get(f"{API}/auth/status").json()["setup_required"] is True


def test_setup_stores_a_password_with_spaces_as_given(client: TestClient) -> None:
    spaced = "  a b c d  "

    assert set_up(client, USERNAME, spaced).status_code == 204

    client.cookies.clear()
    assert log_in(client, USERNAME, spaced).status_code == 204
    assert log_in(client, USERNAME, spaced.strip()).status_code == 401


def test_login_with_the_right_pair_sets_the_cookie_and_the_guarded_call_passes(
    client: TestClient,
) -> None:
    set_up(client)
    client.cookies.clear()
    assert client.get(GUARDED).status_code == 401

    response = log_in(client)

    assert response.status_code == 204
    assert sets_session_cookie(response)
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
    assert error_code(wrong_password) == "invalid_credentials"
    assert error_code(wrong_password) == error_code(wrong_username)
    assert wrong_password.json()["message"] == wrong_username.json()["message"]
    assert not sets_session_cookie(wrong_password)
    assert not sets_session_cookie(wrong_username)
    assert client.get(GUARDED).status_code == 401


def test_login_with_a_blank_or_short_wrong_password_is_401(client: TestClient) -> None:
    set_up(client)
    client.cookies.clear()

    assert log_in(client, USERNAME, " ").status_code == 401
    assert log_in(client, USERNAME, "x").status_code == 401


def test_login_before_setup_is_401(client: TestClient) -> None:
    assert log_in(client).status_code == 401


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("", PASSWORD),
        (USERNAME, ""),
        ("u" * 257, PASSWORD),
        (USERNAME, "p" * 257),
        ("   ", PASSWORD),
    ],
    ids=["empty-username", "empty-password", "long-username", "long-password", "blank-username"],
)
def test_login_rejects_empty_blank_and_over_long_fields(
    client: TestClient, username: str, password: str
) -> None:
    response = log_in(client, username, password)

    assert response.status_code == 400
    assert error_code(response) == "validation_failed"


def test_logout_clears_the_cookie_and_the_guarded_call_fails(client: TestClient) -> None:
    set_up(client)
    assert client.get(GUARDED).status_code == 200

    response = client.post(f"{API}/auth/logout")

    assert response.status_code == 204
    cleared = session_cookie(response)
    emptied = cleared.value == ""
    assert emptied
    assert dict(cleared)["max-age"] == "0"
    assert client.get(GUARDED).status_code == 401


def test_logout_needs_no_session(client: TestClient) -> None:
    assert client.post(f"{API}/auth/logout").status_code == 204


def test_a_garbage_session_cookie_is_401(client: TestClient) -> None:
    set_up(client)
    client.cookies.clear()
    client.cookies.set("tomarr_session", "garbage")

    assert client.get(GUARDED).status_code == 401


def test_session_cookie_attributes_over_http(client: TestClient) -> None:
    # The attributes alone, so a failure report cannot print the cookie value.
    attributes = dict(session_cookie(set_up(client)))

    assert attributes["httponly"] is True
    assert attributes["samesite"] == "lax"
    assert attributes["max-age"] == "2592000"
    assert attributes["path"] == "/"
    assert not attributes["secure"]


def test_session_cookie_is_secure_over_https() -> None:
    with TestClient(create_app(), base_url="https://testserver") as secure_client:
        set_up_response = set_up(secure_client)
        logout_response = secure_client.post(f"{API}/auth/logout")

    assert dict(session_cookie(set_up_response))["secure"] is True
    assert dict(session_cookie(logout_response))["secure"] is True


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


@pytest.mark.parametrize("header", PROXY_HEADERS)
def test_bypass_is_refused_when_a_proxy_header_is_present(tmp_path: Path, header: str) -> None:
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


def test_the_walk_sees_the_command_events_route_as_guarded() -> None:
    app = create_app()

    assert EVENTS_PATH in {route.path for route in iter_route_contexts(app.routes)}
    assert EVENTS_PATH not in unguarded_paths(app)


def test_the_walk_flags_an_unguarded_route() -> None:
    app = create_app()

    @app.get(f"{API}/leak")
    def leak() -> None:
        return None

    def other_dependency() -> None:
        return None

    @app.get(f"{API}/other", dependencies=[Depends(other_dependency)])
    def other() -> None:
        return None

    assert unguarded_paths(app) == [f"{API}/leak", f"{API}/other"]


def test_the_walk_flags_an_unguarded_method_on_a_public_path() -> None:
    app = create_app()

    @app.delete(f"{API}/system/health")
    def remove() -> None:
        return None

    assert unguarded_paths(app) == [f"{API}/system/health"]
