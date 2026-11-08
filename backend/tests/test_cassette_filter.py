from pathlib import Path
from typing import Any

import pytest
from vcr import VCR
from vcr.request import Request

SECRET = "s3cr3t-value"

HEADER_NAMES = ["authorization", "x-api-key", "x-goog-api-key"]
PARAM_NAMES = ["apikey", "api_key", "key", "token"]


def filtered(vcr_config: dict[str, Any], tmp_path: Path, request: Request) -> Request:
    vcr = VCR(cassette_library_dir=str(tmp_path))
    with vcr.use_cassette("filter", **vcr_config) as cassette:
        result = cassette.filter_request(request)
    assert result is not None
    return result


@pytest.mark.parametrize("name", HEADER_NAMES)
def test_header_value_is_filtered(vcr_config: dict[str, Any], tmp_path: Path, name: str) -> None:
    request = Request("GET", "https://example.test/path", None, {name: SECRET})

    result = filtered(vcr_config, tmp_path, request)

    assert SECRET not in str(dict(result.headers))


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_query_value_is_filtered(vcr_config: dict[str, Any], tmp_path: Path, name: str) -> None:
    request = Request("GET", f"https://example.test/path?{name}={SECRET}", None, {})

    result = filtered(vcr_config, tmp_path, request)

    assert SECRET not in result.uri


@pytest.mark.parametrize("name", PARAM_NAMES)
def test_post_value_is_filtered(vcr_config: dict[str, Any], tmp_path: Path, name: str) -> None:
    body = f"{name}={SECRET}".encode()
    request = Request("POST", "https://example.test/path", body, {})

    result = filtered(vcr_config, tmp_path, request)

    assert isinstance(result.body, bytes)
    assert SECRET.encode() not in result.body
