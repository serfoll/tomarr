import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tests.helpers.cassettes import (
    PARAM_NAMES,
    PLACEHOLDER,
    REQUEST_HEADER_NAMES,
    RESPONSE_HEADER_NAMES,
    scan_cassettes,
)

SECRET = "s3cr3t-value"
CASSETTES_DIR = Path(__file__).parent / "fixtures" / "cassettes"


def interaction(
    *,
    method: str = "GET",
    uri: str = "https://api.example.test/v1/items",
    body: str | bytes | None = "",
    request_headers: dict[str, list[str]] | None = None,
    response_headers: dict[str, list[str] | str] | None = None,
) -> dict[str, object]:
    return {
        "request": {
            "body": body,
            "headers": request_headers or {"accept": ["*/*"]},
            "method": method,
            "uri": uri,
        },
        "response": {
            "body": {"string": "{}"},
            "headers": response_headers or {"content-type": ["application/json"]},
            "status": {"code": 200, "message": "OK"},
        },
    }


def multipart(fields: dict[str, str], boundary: str = "b") -> str:
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in fields.items()
    ]
    return "".join(parts) + f"--{boundary}--\r\n"


def write_cassette(
    directory: Path, *interactions: dict[str, object], name: str = "cassette.yaml"
) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"interactions": list(interactions) or [interaction()], "version": 1})
    )
    return path


def test_a_clean_cassette_has_no_offences(tmp_path: Path) -> None:
    write_cassette(
        tmp_path,
        interaction(uri="https://api.example.test/v1/items?page=2&q=dandadan", body="page=2"),
    )

    assert scan_cassettes(tmp_path) == []


@pytest.mark.parametrize("name", REQUEST_HEADER_NAMES)
def test_a_request_header_with_a_value_is_an_offence(tmp_path: Path, name: str) -> None:
    write_cassette(tmp_path, interaction(request_headers={name: [SECRET]}))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"request header {name}" in offences[0]


@pytest.mark.parametrize("name", ["Cookie", "COOKIE", "Authorization", "X-Api-Key"])
def test_request_header_names_match_case_insensitively(tmp_path: Path, name: str) -> None:
    write_cassette(tmp_path, interaction(request_headers={name: [SECRET]}))

    assert len(scan_cassettes(tmp_path)) == 1


@pytest.mark.parametrize("name", [*RESPONSE_HEADER_NAMES, "Set-Cookie", "SET-COOKIE"])
@pytest.mark.parametrize("value", [[SECRET], [SECRET, PLACEHOLDER], SECRET])
def test_a_response_header_with_a_value_is_an_offence(
    tmp_path: Path, name: str, value: list[str] | str
) -> None:
    write_cassette(tmp_path, interaction(response_headers={name: value}))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"response header {name}" in offences[0]


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_a_query_value_is_an_offence(tmp_path: Path, name: str) -> None:
    write_cassette(tmp_path, interaction(uri=f"https://api.example.test/v1?page=2&{name}={SECRET}"))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"query parameter {name}" in offences[0]


# AniList's docs name access_token as its OAuth token. The cases above read PARAM_NAMES, so
# this one names it outright.
def test_an_anilist_access_token_is_an_offence(tmp_path: Path) -> None:
    write_cassette(tmp_path, interaction(uri=f"https://api.example.test/v1?access_token={SECRET}"))

    assert "access_token" in PARAM_NAMES
    assert len(scan_cassettes(tmp_path)) == 1


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_a_form_value_is_an_offence(tmp_path: Path, name: str) -> None:
    write_cassette(tmp_path, interaction(method="POST", body=f"remember=1&{name}={SECRET}"))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"form field {name}" in offences[0]


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_a_json_body_key_is_an_offence(tmp_path: Path, name: str) -> None:
    write_cassette(tmp_path, interaction(method="POST", body=json.dumps({name: SECRET, "page": 1})))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"JSON key {name}" in offences[0]


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_a_multipart_field_is_an_offence(tmp_path: Path, name: str) -> None:
    write_cassette(
        tmp_path,
        interaction(
            method="POST",
            body=multipart({"remember": "1", name: SECRET}),
            request_headers={"content-type": ["multipart/form-data; boundary=b"]},
        ),
    )

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"multipart field {name}" in offences[0]


# The boundary is read from the body's first line, so a missing or odd Content-Type still scans.
@pytest.mark.parametrize("content_type", [None, "application/octet-stream"])
def test_a_multipart_body_is_scanned_whatever_the_content_type(
    tmp_path: Path, content_type: str | None
) -> None:
    headers = {"content-type": [content_type]} if content_type else None
    body = multipart({"username": "alice", "password": SECRET}, boundary="x-7f3a")
    write_cassette(tmp_path, interaction(method="POST", body=body, request_headers=headers))

    assert len(scan_cassettes(tmp_path)) == 2


@pytest.mark.parametrize("name", ["ApiKey", "APIKEY", "Password", "UserName", "Client_Secret"])
@pytest.mark.parametrize(
    ("where", "make"),
    [
        (
            "query parameter",
            lambda name: interaction(uri=f"https://api.example.test/v1?{name}={SECRET}"),
        ),
        ("form field", lambda name: interaction(method="POST", body=f"{name}={SECRET}")),
        (
            "multipart field",
            lambda name: interaction(method="POST", body=multipart({name: SECRET})),
        ),
        ("JSON key", lambda name: interaction(method="POST", body=json.dumps({name: SECRET}))),
    ],
)
def test_field_names_match_case_insensitively(
    tmp_path: Path, name: str, where: str, make: Callable[[str], dict[str, object]]
) -> None:
    write_cassette(tmp_path, make(name))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert f"{where} {name}" in offences[0]


def test_a_nested_json_key_is_an_offence(tmp_path: Path) -> None:
    body = json.dumps({"variables": {"filters": [{"password": SECRET}]}})
    write_cassette(tmp_path, interaction(method="POST", body=body))

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert "JSON key password" in offences[0]


# vcrpy's body filters skip PUT and PATCH, and read JSON only when Content-Type is exactly
# application/json. The scan decides by shape, so it still catches both.
@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_a_login_sent_as_put_or_patch_is_an_offence(tmp_path: Path, method: str) -> None:
    write_cassette(tmp_path, interaction(method=method, body=f"username=admin&password={SECRET}"))

    assert len(scan_cassettes(tmp_path)) == 2


def test_a_json_body_with_a_charset_content_type_is_an_offence(tmp_path: Path) -> None:
    write_cassette(
        tmp_path,
        interaction(
            method="POST",
            body=json.dumps({"password": SECRET}),
            request_headers={"content-type": ["application/json; charset=utf-8"]},
        ),
    )

    assert len(scan_cassettes(tmp_path)) == 1


def test_a_binary_body_is_scanned(tmp_path: Path) -> None:
    write_cassette(tmp_path, interaction(method="POST", body=f"password={SECRET}".encode()))

    assert len(scan_cassettes(tmp_path)) == 1


@pytest.mark.parametrize("body", [None, "", "not a form, not json", b"\xff\xfe\x00"])
def test_a_body_without_fields_is_not_an_offence(tmp_path: Path, body: str | bytes | None) -> None:
    write_cassette(tmp_path, interaction(method="POST", body=body))

    assert scan_cassettes(tmp_path) == []


@pytest.mark.parametrize(
    "item",
    [
        pytest.param(
            interaction(request_headers={name: [PLACEHOLDER]}), id=f"request header {name}"
        )
        for name in REQUEST_HEADER_NAMES
    ]
    + [
        pytest.param(
            interaction(response_headers={name: [PLACEHOLDER]}), id=f"response header {name}"
        )
        for name in RESPONSE_HEADER_NAMES
    ]
    + [
        pytest.param(
            interaction(response_headers={name: PLACEHOLDER}), id=f"response header {name} string"
        )
        for name in RESPONSE_HEADER_NAMES
    ]
    + [
        pytest.param(
            interaction(uri=f"https://api.example.test/v1?{name}={PLACEHOLDER}"),
            id=f"query parameter {name}",
        )
        for name in PARAM_NAMES
    ]
    + [
        pytest.param(
            interaction(method="POST", body=f"{name}={PLACEHOLDER}"), id=f"form field {name}"
        )
        for name in PARAM_NAMES
    ]
    + [
        pytest.param(
            interaction(method="POST", body=multipart({name: PLACEHOLDER})),
            id=f"multipart field {name}",
        )
        for name in PARAM_NAMES
    ]
    + [
        pytest.param(
            interaction(method="POST", body=json.dumps({name: PLACEHOLDER})),
            id=f"JSON key {name}",
        )
        for name in PARAM_NAMES
    ],
)
def test_the_placeholder_is_not_an_offence(tmp_path: Path, item: dict[str, object]) -> None:
    write_cassette(tmp_path, item)

    assert scan_cassettes(tmp_path) == []


def test_an_offence_names_the_cassette_the_interaction_and_the_field_but_not_the_value(
    tmp_path: Path,
) -> None:
    write_cassette(
        tmp_path,
        interaction(),
        interaction(request_headers={"cookie": [SECRET]}),
        name="provider/login.yaml",
    )

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert "provider/login.yaml" in offences[0]
    assert "interaction 1" in offences[0]
    assert "request header cookie" in offences[0]
    assert SECRET not in offences[0]


@pytest.mark.parametrize(
    "item",
    [
        interaction(request_headers={"cookie": [SECRET]}),
        interaction(response_headers={"set-cookie": [SECRET]}),
        interaction(uri=f"https://api.example.test/v1?apikey={SECRET}"),
        interaction(method="POST", body=f"password={SECRET}"),
        interaction(method="POST", body=multipart({"password": SECRET})),
        interaction(method="POST", body=json.dumps({"password": SECRET})),
    ],
)
def test_no_offence_message_contains_the_value(tmp_path: Path, item: dict[str, object]) -> None:
    write_cassette(tmp_path, item)

    offences = scan_cassettes(tmp_path)

    assert offences
    assert SECRET not in "\n".join(offences)


def test_every_cassette_under_the_directory_is_scanned(tmp_path: Path) -> None:
    write_cassette(tmp_path, name="clean.yaml")
    write_cassette(
        tmp_path,
        interaction(request_headers={"cookie": [SECRET]}),
        name="deep/er/dirty.yaml",
    )

    offences = scan_cassettes(tmp_path)

    assert len(offences) == 1
    assert "deep/er/dirty.yaml" in offences[0]


def test_the_committed_cassettes_have_no_offences() -> None:
    assert scan_cassettes(CASSETTES_DIR) == []
