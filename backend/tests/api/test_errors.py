import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tomarr.api.errors import ERRORS
from tomarr.app import create_app
from tomarr.core.errors import ErrorCode

API = "/api/v1"
SETUP = f"{API}/auth/setup"
FAILURE_DETAIL = "disk quota hit at /config/tomarr.db"
SUBMITTED_PASSWORD = "Qz7#v"
ERROR_RESPONSE_REF = {"$ref": "#/components/schemas/ErrorResponse"}


def log_lines(tmp_path: Path) -> list[dict[str, object]]:
    text = (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def failing_app() -> FastAPI:
    app = create_app()

    @app.get(f"{API}/boom")
    def boom() -> None:
        raise RuntimeError(FAILURE_DETAIL)

    return app


def test_every_error_code_has_a_status_and_a_message() -> None:
    assert set(ERRORS) == set(ErrorCode)
    for status, message in ERRORS.values():
        assert 400 <= status <= 599
        assert message


def test_an_unexpected_exception_is_500_with_the_generic_body_and_no_detail() -> None:
    with TestClient(failing_app(), raise_server_exceptions=False) as client:
        response = client.get(f"{API}/boom")

    assert response.status_code == 500
    request_id = response.headers["x-request-id"]
    assert response.json() == {
        "code": "internal_error",
        "message": ERRORS[ErrorCode.INTERNAL_ERROR].message,
        "request_id": request_id,
    }
    leaks = [
        text for text in ("Traceback", "RuntimeError", FAILURE_DETAIL) if text in response.text
    ]
    assert leaks == []


def test_the_500_log_line_has_the_stack_and_the_same_request_id(tmp_path: Path) -> None:
    with TestClient(failing_app(), raise_server_exceptions=False) as client:
        response = client.get(f"{API}/boom", headers={"X-Request-ID": "trace-500"})

    assert response.headers["x-request-id"] == "trace-500"
    assert response.json()["request_id"] == "trace-500"
    errors = [line for line in log_lines(tmp_path) if line["level"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["request_id"] == "trace-500"
    exception = str(errors[0]["exception"])
    assert "Traceback" in exception
    assert FAILURE_DETAIL in exception


def test_a_validation_error_is_400_with_the_code_and_request_id(client: TestClient) -> None:
    response = client.post(SETUP, data={"username": "reader", "password": SUBMITTED_PASSWORD})

    assert response.status_code == 400
    assert response.json() == {
        "code": "validation_failed",
        "message": ERRORS[ErrorCode.VALIDATION_FAILED].message,
        "request_id": response.headers["x-request-id"],
    }
    echoed = SUBMITTED_PASSWORD in response.text
    assert not echoed


def test_a_validation_error_is_logged_with_locations_and_types_only(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            SETUP,
            data={"username": "reader", "password": SUBMITTED_PASSWORD},
            headers={"X-Request-ID": "trace-400"},
        )

    assert response.status_code == 400
    lines = [line for line in log_lines(tmp_path) if line.get("request_id") == "trace-400"]
    assert [line["errors"] for line in lines] == [
        [{"loc": ["body", "password"], "type": "string_too_short"}]
    ]
    logged = SUBMITTED_PASSWORD in (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
    assert not logged


def test_a_hostile_inbound_id_does_not_reach_the_log(tmp_path: Path) -> None:
    hostile = 'x\n{"level": "ERROR", "message": "forged"}'
    with TestClient(create_app()) as client:
        response = client.post(SETUP, headers={"X-Request-ID": hostile})

    request_id = response.headers["x-request-id"]
    logged = [line for line in log_lines(tmp_path) if "errors" in line]
    assert [line["request_id"] for line in logged] == [request_id]
    forged = "forged" in (tmp_path / "logs" / "tomarr.log").read_text(encoding="utf-8")
    assert not forged


def test_an_unknown_path_is_404_with_the_shape(client: TestClient) -> None:
    response = client.get(f"{API}/nowhere")

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "message": ERRORS[ErrorCode.NOT_FOUND].message,
        "request_id": response.headers["x-request-id"],
    }


def test_a_wrong_method_is_405_with_the_shape_and_keeps_allow(client: TestClient) -> None:
    response = client.post(f"{API}/system/health")

    assert response.status_code == 405
    assert response.json() == {
        "code": "method_not_allowed",
        "message": ERRORS[ErrorCode.METHOD_NOT_ALLOWED].message,
        "request_id": response.headers["x-request-id"],
    }
    assert "GET" in response.headers["allow"]


def test_another_http_error_keeps_its_status_with_the_generic_code() -> None:
    app = create_app()

    @app.get(f"{API}/gone")
    def gone() -> None:
        raise HTTPException(410, "secret internal reason")

    with TestClient(app) as client:
        response = client.get(f"{API}/gone")

    assert response.status_code == 410
    assert response.json() == {
        "code": "http_error",
        "message": ERRORS[ErrorCode.HTTP_ERROR].message,
        "request_id": response.headers["x-request-id"],
    }


def test_openapi_declares_error_response_on_400_401_409_and_500() -> None:
    paths = create_app().openapi()["paths"]

    def schema(path: str, method: str, status: str) -> object:
        return paths[path][method]["responses"][status]["content"]["application/json"]["schema"]

    assert schema(SETUP, "post", "400") == ERROR_RESPONSE_REF
    assert schema(f"{API}/auth/login", "post", "401") == ERROR_RESPONSE_REF
    assert schema(f"{API}/system/status", "get", "401") == ERROR_RESPONSE_REF
    assert schema(SETUP, "post", "409") == ERROR_RESPONSE_REF
    for path, operations in paths.items():
        for method in operations:
            assert schema(path, method, "500") == ERROR_RESPONSE_REF


def test_openapi_has_no_validation_422_or_its_schemas() -> None:
    schema = create_app().openapi()

    statuses = {
        status
        for operations in schema["paths"].values()
        for operation in operations.values()
        for status in operation["responses"]
    }
    assert "422" not in statuses
    names = set(schema["components"]["schemas"])
    assert names.isdisjoint({"HTTPValidationError", "ValidationError"})


def test_openapi_describes_the_error_response_shape() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    assert schemas["ErrorResponse"]["required"] == ["code", "message", "request_id"]
    assert set(schemas["ErrorResponse"]["properties"]) == {"code", "message", "request_id"}
    assert set(schemas["ErrorCode"]["enum"]) == {code.value for code in ErrorCode}


def test_openapi_rewrite_survives_a_route_added_later() -> None:
    app = create_app()
    app.openapi()

    @app.post(f"{API}/later")
    def later(count: int) -> None:
        return None

    responses = app.openapi()["paths"][f"{API}/later"]["post"]["responses"]
    assert "422" not in responses
    assert responses["400"]["content"]["application/json"]["schema"] == ERROR_RESPONSE_REF


def test_the_served_openapi_document_is_the_rewritten_one(client: TestClient) -> None:
    responses = client.get("/openapi.json").json()["paths"][SETUP]["post"]["responses"]

    assert "422" not in responses
    assert responses["400"]["content"]["application/json"]["schema"] == ERROR_RESPONSE_REF
