import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict
from urllib.parse import parse_qsl, urlsplit

import yaml

REQUEST_HEADER_NAMES = ["authorization", "x-api-key", "x-goog-api-key", "cookie"]
RESPONSE_HEADER_NAMES = ["set-cookie"]
PARAM_NAMES = [
    "apikey",
    "token",
    "username",
    "password",
    "apiKey",
    "refreshToken",
    "client_secret",
]
PLACEHOLDER = "REDACTED"

_PARAM_NAMES_FOLDED = {name.lower() for name in PARAM_NAMES}
_PART_NAME = re.compile(r'^content-disposition:.*?\bname="([^"]*)"', re.IGNORECASE | re.MULTILINE)


Headers = dict[str, str | list[str]]


class Response(TypedDict):
    status: dict[str, object]
    headers: Headers
    body: dict[str, object]


def redact_response_headers(response: Response) -> Response:
    """A vcrpy before_record_response hook. vcrpy's own header filters only touch requests.
    The value keeps its shape, since replay iterates a list of values."""
    headers = response["headers"]
    for name, value in headers.items():
        if name.lower() in RESPONSE_HEADER_NAMES:
            headers[name] = [PLACEHOLDER] * len(value) if isinstance(value, list) else PLACEHOLDER
    return response


def scan_cassettes(directory: Path) -> list[str]:
    """One message per header, query value, form value, multipart field or JSON key that is named
    in the lists above and holds anything but the placeholder. A message never contains the value.

    Bodies are checked by shape, not by method or Content-Type, because vcrpy's filters skip PUT
    and PATCH and read JSON only for exactly application/json. A multipart boundary is read from
    the body's first line for the same reason.

    Query, form, multipart and JSON names match case-insensitively because ASP.NET servers such as
    Prowlarr and Kavita accept any casing, while vcrpy's filters match exactly, so a spelling the
    filters miss fails here and the remedy is to add it to the lists."""
    offences: list[str] = []
    for path in sorted(directory.rglob("*.yaml")):
        cassette = yaml.safe_load(path.read_text())
        for index, item in enumerate(cassette["interactions"]):
            request, response = item["request"], item["response"]
            found = _unredacted(
                request["headers"], response["headers"], request["uri"], request["body"]
            )
            offences.extend(
                f"{path.relative_to(directory)}: interaction {index}: {where} {name} "
                f"is not {PLACEHOLDER}"
                for where, name in found
            )
    return offences


def _unredacted(
    request_headers: Headers, response_headers: Headers, uri: str, body: str | bytes | None
) -> Iterator[tuple[str, str]]:
    yield from _headers("request", request_headers, REQUEST_HEADER_NAMES)
    yield from _headers("response", response_headers, RESPONSE_HEADER_NAMES)
    yield from _fields("query parameter", parse_qsl(urlsplit(uri).query, keep_blank_values=True))
    if isinstance(body, bytes):
        body = body.decode(errors="replace")
    if body is None:
        return
    yield from _fields("form field", parse_qsl(body, keep_blank_values=True))
    yield from _fields("multipart field", _multipart_fields(body))
    try:
        parsed = json.loads(body)
    except ValueError:
        return
    yield from _json_keys(parsed)


def _headers(side: str, headers: Headers, names: list[str]) -> Iterator[tuple[str, str]]:
    for name, value in headers.items():
        values = [value] if isinstance(value, str) else value
        if name.lower() in names and any(v != PLACEHOLDER for v in values):
            yield f"{side} header", name


def _fields(where: str, pairs: list[tuple[str, str]]) -> Iterator[tuple[str, str]]:
    for name, value in pairs:
        if name.lower() in _PARAM_NAMES_FOLDED and value != PLACEHOLDER:
            yield where, name


def _multipart_fields(body: str) -> list[tuple[str, str]]:
    first_line = body.split("\r\n", 1)[0].rstrip()
    if not first_line.startswith("--") or len(first_line) < 3:
        return []
    fields: list[tuple[str, str]] = []
    for part in body.split(first_line)[1:]:
        head, separator, content = part.partition("\r\n\r\n")
        match = _PART_NAME.search(head)
        if separator and match:
            fields.append((match.group(1), content.removesuffix("\r\n")))
    return fields


def _json_keys(data: object) -> Iterator[tuple[str, str]]:
    if isinstance(data, dict):
        for name, value in data.items():
            if name.lower() in _PARAM_NAMES_FOLDED and value != PLACEHOLDER:
                yield "JSON key", name
            else:
                yield from _json_keys(value)
    elif isinstance(data, list):
        for item in data:
            yield from _json_keys(item)
