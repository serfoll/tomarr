from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from tests.api.test_auth import unguarded_paths
from tomarr.app import create_app
from tomarr.core.errors import ErrorCode

INDEX = "<!doctype html><title>Tomarr</title><div id=root></div>"
SCRIPT = "console.log('tomarr');"
SECRET = "not for the browser"
HEALTH = "/api/v1/system/health"
CATCH_ALL = "/{path:path}"


@pytest.fixture
def build_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "dist"
    (directory / "assets").mkdir(parents=True)
    (directory / "index.html").write_text(INDEX)
    (directory / "assets" / "app.js").write_text(SCRIPT)
    (tmp_path / "secret.txt").write_text(SECRET)
    monkeypatch.setenv("TOMARR_STATIC_DIR", str(directory))
    return directory


@pytest.fixture
def static_client(build_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_the_root_is_index_html(static_client: TestClient) -> None:
    response = static_client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == INDEX


def test_an_asset_is_served_as_javascript(static_client: TestClient) -> None:
    response = static_client.get("/assets/app.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.text == SCRIPT


def test_a_client_route_is_index_html(static_client: TestClient) -> None:
    response = static_client.get("/series/1")

    assert response.status_code == 200
    assert response.text == INDEX


def test_head_on_the_root_has_headers_and_no_body(static_client: TestClient) -> None:
    response = static_client.head("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.content == b""


def test_a_write_method_on_a_static_path_is_405(static_client: TestClient) -> None:
    response = static_client.post("/series/1")

    assert response.status_code == 405
    assert response.json()["code"] == ErrorCode.METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "GET, HEAD"


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("POST", HEALTH, "GET"),
        ("POST", "/api/v1/system/status", "GET"),
        ("PUT", "/api/v1/auth/login", "POST"),
        ("GET", "/api/v1/auth/login", "POST"),
    ],
)
def test_a_wrong_method_on_an_api_route_stays_405(
    static_client: TestClient, method: str, path: str, allowed: str
) -> None:
    response = static_client.request(method, path)

    assert response.status_code == 405
    assert response.json() == {
        "code": "method_not_allowed",
        "message": "This address does not accept that method.",
        "request_id": response.headers["x-request-id"],
    }
    assert response.headers["allow"] == allowed


@pytest.mark.parametrize("path", ["/api", "/api/v1/does-not-exist", "/api/anything/else"])
def test_an_unknown_api_path_is_the_json_404(static_client: TestClient, path: str) -> None:
    response = static_client.get(path)

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "Nothing exists at this address.",
        "request_id": response.headers["x-request-id"],
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/nope"),
        ("PUT", "/api/v1/nope"),
        ("PATCH", "/api/v1/nope"),
        ("DELETE", "/api/v1/nope"),
        ("OPTIONS", "/api/v1/nope"),
        ("POST", "/api"),
    ],
)
def test_a_write_method_on_an_unknown_api_path_is_the_json_404(
    static_client: TestClient, method: str, path: str
) -> None:
    response = static_client.request(method, path)

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": "Nothing exists at this address.",
        "request_id": response.headers["x-request-id"],
    }


def test_head_on_an_unknown_api_path_is_a_404_without_html(static_client: TestClient) -> None:
    response = static_client.head("/api/v1/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("path", ["/assets/old-hash.js", "/assets/", "/assets/" + "a" * 256])
def test_a_missing_asset_is_the_json_404_not_index_html(
    static_client: TestClient, path: str
) -> None:
    response = static_client.get(path)

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    "path",
    ["/" + "a" * 256, "/series/" + "a" * 1100, "/" + "/".join(["b" * 250] * 200)],
)
def test_a_path_too_long_for_the_file_system_is_a_client_route(
    static_client: TestClient, path: str
) -> None:
    response = static_client.get(path)

    assert response.status_code == 200
    assert response.text == INDEX


def test_api_routes_still_answer(static_client: TestClient) -> None:
    response = static_client.get(HEALTH)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_openapi_document_answers_and_leaves_the_catch_all_out(
    static_client: TestClient,
) -> None:
    response = static_client.get("/openapi.json")

    assert response.status_code == 200
    assert HEALTH in response.json()["paths"]
    assert CATCH_ALL not in response.json()["paths"]


def test_the_docs_page_is_not_index_html(static_client: TestClient) -> None:
    response = static_client.get("/docs")

    assert response.status_code == 200
    assert response.text != INDEX
    assert "swagger" in response.text.lower()


@pytest.mark.parametrize(
    "path",
    [
        "/..%2f..%2f..%2f..%2f..%2f..%2f..%2f..%2fetc/passwd",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/%2e%2e%2fsecret.txt",
        "/..%5csecret.txt",
    ],
)
def test_a_traversal_path_never_returns_a_file_outside_the_build(
    static_client: TestClient, path: str
) -> None:
    response = static_client.get(path)

    assert SECRET not in response.text
    assert response.text == INDEX


def test_an_absolute_path_never_returns_a_file_outside_the_build(
    static_client: TestClient, build_dir: Path
) -> None:
    secret = build_dir.parent / "secret.txt"

    response = static_client.get(f"/{quote(str(secret), safe='')}")

    assert SECRET not in response.text
    assert response.text == INDEX


def test_a_symlink_to_outside_the_build_is_not_followed(
    static_client: TestClient, build_dir: Path
) -> None:
    (build_dir / "leak.txt").symlink_to(build_dir.parent / "secret.txt")

    response = static_client.get("/leak.txt")

    assert SECRET not in response.text
    assert response.text == INDEX


def test_a_path_with_a_null_byte_is_a_client_route_not_a_server_error(
    static_client: TestClient,
) -> None:
    response = static_client.get("/%00")

    assert response.status_code == 200
    assert response.text == INDEX


def test_the_app_without_a_build_directory_serves_the_api_and_a_json_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOMARR_STATIC_DIR", str(tmp_path / "missing"))

    with TestClient(create_app()) as client:
        assert client.get(HEALTH).status_code == 200
        response = client.get("/")

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.NOT_FOUND


def test_a_build_without_index_html_is_not_served(
    build_dir: Path,
) -> None:
    (build_dir / "index.html").unlink()

    with TestClient(create_app()) as client:
        response = client.get("/series/1")

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.NOT_FOUND


def test_the_catch_all_is_outside_the_default_deny_walk(build_dir: Path) -> None:
    app = create_app()

    assert CATCH_ALL in {route.path for route in iter_route_contexts(app.routes)}
    assert unguarded_paths(app) == []
