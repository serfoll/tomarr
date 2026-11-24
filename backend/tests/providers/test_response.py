import logging

import httpx2
import pytest

from tomarr.core.errors import ProviderError
from tomarr.providers.response import (
    read_response,
    require_base36,
    require_digits,
    require_uuid,
)

SECRET_TEXT = "s3cr3t body text"


@pytest.mark.parametrize(
    "content",
    [
        f"<html>{SECRET_TEXT}</html>".encode(),
        b"\xff\xfe" + SECRET_TEXT.encode(),
        b"[" * 200_000 + SECRET_TEXT.encode(),
    ],
    ids=["not-json", "not-utf8", "too-deep"],
)
async def test_an_unreadable_body_is_logged_by_kind_without_its_text(
    content: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    response = httpx2.Response(200, content=content)

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError) as raised:
        read_response("Example", response, lambda payload: payload)

    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert "Example" in caplog.records[0].getMessage()
    assert SECRET_TEXT not in caplog.records[0].getMessage()
    assert SECRET_TEXT not in str(raised.value)
    assert raised.value.provider == "Example"
    assert raised.value.status == 200


@pytest.mark.parametrize("provider", ["AniList", "MangaBaka"])
def test_an_id_that_is_not_digits_is_refused_with_the_providers_name(provider: str) -> None:
    with pytest.raises(ValueError) as raised:
        require_digits(provider, "12x")

    assert str(raised.value) == f"{provider} series IDs are made of digits only."


@pytest.mark.parametrize(
    "provider_id", ["68112dc1-2b80-4f20-beb8-2f2a8716a430", "68112DC1-2B80-4F20-BEB8-2F2A8716A430"]
)
def test_a_uuid_is_accepted_in_either_case(provider_id: str) -> None:
    require_uuid("MangaDex", provider_id)


@pytest.mark.parametrize(
    "provider_id",
    [
        "",
        "12x",
        "68112dc12b804f208beb82f2a8716a430",
        "{68112dc1-2b80-4f20-beb8-2f2a8716a430}",
        "urn:uuid:68112dc1-2b80-4f20-beb8-2f2a8716a430",
        "68112dc1-2b80-4f20-beb8-2f2a8716a430\n",
        "68112dc1-2b80-4f20-beb8-2f2a8716a430/../x",
        "68112dc1-2b80-4f20-beb8-2f2a8716a43g",
        "\u0661" * 8 + "-2b80-4f20-beb8-2f2a8716a430",
    ],
)
def test_an_id_that_is_not_a_uuid_is_refused_with_the_providers_name(provider_id: str) -> None:
    with pytest.raises(ValueError) as raised:
        require_uuid("MangaDex", provider_id)

    assert str(raised.value) == "MangaDex series IDs are UUIDs."


@pytest.mark.parametrize("provider_id", ["ugf5dzu", "0", "09az", "z" * 12])
def test_lowercase_letters_and_digits_are_a_base_36_id(provider_id: str) -> None:
    require_base36("MangaUpdates", provider_id)


@pytest.mark.parametrize(
    "provider_id",
    [
        "",
        "UGF5DZU",
        "ugf5dzu\n",
        " ugf5dzu",
        "ugf5dzu/../x",
        "../x",
        "1/2",
        "-1",
        "1.5",
        "\u0661\u0662",
        "z" * 13,
        "0" * 2900,
    ],
)
def test_an_id_that_is_not_base_36_is_refused_with_the_providers_name(provider_id: str) -> None:
    with pytest.raises(ValueError) as raised:
        require_base36("MangaUpdates", provider_id)

    assert str(raised.value) == "MangaUpdates series IDs are up to 12 digits and lowercase letters."
