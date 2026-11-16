import logging

import httpx2
import pytest

from tomarr.core.errors import ProviderError
from tomarr.providers.response import read_response, require_digits

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
