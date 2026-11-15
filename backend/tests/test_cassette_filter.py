import json
from pathlib import Path

import pytest
from vcr import VCR
from vcr.request import Request

from tests.helpers.cassettes import (
    PARAM_NAMES,
    PLACEHOLDER,
    REQUEST_HEADER_NAMES,
    RESPONSE_HEADER_NAMES,
    Response,
    redact_response_headers,
)

SECRET = "s3cr3t-value"


def filtered(vcr_config: dict[str, object], tmp_path: Path, request: Request) -> Request:
    vcr = VCR(cassette_library_dir=str(tmp_path))
    with vcr.use_cassette("filter", **vcr_config) as cassette:
        result = cassette.filter_request(request)
    assert result is not None
    return result


@pytest.mark.parametrize("name", REQUEST_HEADER_NAMES)
def test_header_value_is_filtered(vcr_config: dict[str, object], tmp_path: Path, name: str) -> None:
    request = Request("GET", "https://example.test/path", None, {name: SECRET})

    result = filtered(vcr_config, tmp_path, request)

    assert SECRET not in str(dict(result.headers))


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_query_value_is_filtered(vcr_config: dict[str, object], tmp_path: Path, name: str) -> None:
    request = Request("GET", f"https://example.test/path?{name}={SECRET}", None, {})

    result = filtered(vcr_config, tmp_path, request)

    assert SECRET not in result.uri


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_post_value_is_filtered(vcr_config: dict[str, object], tmp_path: Path, name: str) -> None:
    body = f"{name}={SECRET}".encode()
    request = Request("POST", "https://example.test/path", body, {})

    result = filtered(vcr_config, tmp_path, request)

    assert isinstance(result.body, bytes)
    assert SECRET.encode() not in result.body


@pytest.mark.parametrize("name", REQUEST_HEADER_NAMES)
def test_header_value_becomes_the_placeholder(
    vcr_config: dict[str, object], tmp_path: Path, name: str
) -> None:
    request = Request("GET", "https://example.test/path", None, {name: SECRET})

    result = filtered(vcr_config, tmp_path, request)

    assert result.headers[name] == PLACEHOLDER


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_query_value_becomes_the_placeholder(
    vcr_config: dict[str, object], tmp_path: Path, name: str
) -> None:
    request = Request("GET", f"https://example.test/path?{name}={SECRET}", None, {})

    result = filtered(vcr_config, tmp_path, request)

    assert result.uri == f"https://example.test/path?{name}={PLACEHOLDER}"


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_post_value_becomes_the_placeholder(
    vcr_config: dict[str, object], tmp_path: Path, name: str
) -> None:
    request = Request("POST", "https://example.test/path", f"{name}={SECRET}".encode(), {})

    result = filtered(vcr_config, tmp_path, request)

    assert result.body == f"{name}={PLACEHOLDER}".encode()


# Query, form and JSON names match exactly, so Kavita's apiKey is not covered by apikey.
PROVIDER_PARAM_NAMES = ["apiKey", "refreshToken", "client_secret"]


@pytest.mark.parametrize("name", PROVIDER_PARAM_NAMES)
def test_provider_param_is_replaced_in_query_form_and_json(
    vcr_config: dict[str, object], tmp_path: Path, name: str
) -> None:
    query = Request("GET", f"https://example.test/path?{name}={SECRET}", None, {})
    form = Request("POST", "https://example.test/path", f"{name}={SECRET}".encode(), {})
    nested = json.dumps({"variables": {"input": {name: SECRET}}}).encode()
    body = Request(
        "POST", "https://example.test/path", nested, {"Content-Type": "application/json"}
    )

    assert (
        filtered(vcr_config, tmp_path, query).uri
        == f"https://example.test/path?{name}={PLACEHOLDER}"
    )
    assert filtered(vcr_config, tmp_path, form).body == f"{name}={PLACEHOLDER}".encode()
    result = filtered(vcr_config, tmp_path, body).body
    assert isinstance(result, bytes)
    assert json.loads(result) == {"variables": {"input": {name: PLACEHOLDER}}}


def test_login_form_fields_are_replaced_next_to_untouched_ones(
    vcr_config: dict[str, object], tmp_path: Path
) -> None:
    body = f"username=admin&password={SECRET}&remember=1".encode()
    request = Request("POST", "https://example.test/login", body, {})

    result = filtered(vcr_config, tmp_path, request)

    assert result.body == f"username={PLACEHOLDER}&password={PLACEHOLDER}&remember=1".encode()


# vcrpy reads a body as JSON only when Content-Type is exactly application/json. A value such as
# "application/json; charset=utf-8" falls through to form parsing and the fields are not filtered.
def test_login_fields_are_replaced_in_a_json_body(
    vcr_config: dict[str, object], tmp_path: Path
) -> None:
    body = json.dumps({"username": "admin", "password": SECRET, "remember": True}).encode()
    request = Request(
        "POST", "https://example.test/login", body, {"Content-Type": "application/json"}
    )

    result = filtered(vcr_config, tmp_path, request)

    assert isinstance(result.body, bytes)
    assert json.loads(result.body) == {
        "username": PLACEHOLDER,
        "password": PLACEHOLDER,
        "remember": True,
    }


def test_a_nested_json_key_is_replaced(vcr_config: dict[str, object], tmp_path: Path) -> None:
    body = json.dumps({"variables": {"password": SECRET, "page": 1}}).encode()
    request = Request(
        "POST", "https://example.test/graphql", body, {"Content-Type": "application/json"}
    )

    result = filtered(vcr_config, tmp_path, request)

    assert isinstance(result.body, bytes)
    assert json.loads(result.body) == {"variables": {"password": PLACEHOLDER, "page": 1}}


# httpx2 hands vcrpy lowercase header names with a list of values, one per header line.
# Other clients keep the server's casing, so the hook matches names case-insensitively.
@pytest.mark.parametrize("header", ["set-cookie", "Set-Cookie", "SET-COOKIE"])
@pytest.mark.parametrize("value", [f"sid={SECRET}", [f"sid={SECRET}", f"csrf={SECRET}"]])
def test_set_cookie_response_header_becomes_the_placeholder(
    header: str, value: str | list[str]
) -> None:
    response = Response(
        status={"code": 200},
        headers={header: value, "content-type": ["text/html"]},
        body={"string": b""},
    )

    result = redact_response_headers(response)

    assert result["headers"]["content-type"] == ["text/html"]
    assert SECRET not in str(result["headers"])
    redacted = result["headers"][header]
    if isinstance(value, str):
        assert redacted == PLACEHOLDER
    else:
        assert redacted == [PLACEHOLDER] * len(value)


def test_cookies_and_login_fields_are_in_the_name_lists() -> None:
    assert "cookie" in REQUEST_HEADER_NAMES
    assert "set-cookie" in RESPONSE_HEADER_NAMES
    assert {"username", "password"} <= set(PARAM_NAMES)


def test_vcr_config_redacts_response_headers_when_recording(
    vcr_config: dict[str, object], tmp_path: Path
) -> None:
    name = "set-cookie"
    vcr = VCR(cassette_library_dir=str(tmp_path))
    request = Request("GET", "https://example.test/path", None, {})
    response = Response(
        status={"code": 200}, headers={name: [f"sid={SECRET}"]}, body={"string": b""}
    )

    with vcr.use_cassette("filter", **vcr_config) as cassette:
        cassette.append(request, response)
        recorded = cassette.data[0][1]

    assert recorded["headers"] == {name: [PLACEHOLDER]}
