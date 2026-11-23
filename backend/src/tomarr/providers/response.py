import logging
import re
from collections.abc import Callable

import httpx2
from pydantic import ValidationError

from tomarr.core.errors import ProviderError

logger = logging.getLogger(__name__)

# What a body can raise when it is not JSON, not UTF-8, not the shape the parser reads
# (ValidationError is a ValueError), or nested too deep.
UNREADABLE = (ValueError, RecursionError)


def require_digits(provider: str, provider_id: str) -> None:
    # The ID goes into a path or a query variable, so anything but digits could reach another one.
    if not (provider_id.isascii() and provider_id.isdigit()):
        raise ValueError(f"{provider} series IDs are made of digits only.")


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def require_uuid(provider: str, provider_id: str) -> None:
    # Not uuid.UUID(), which also takes braces, a urn: prefix and hyphen-less forms.
    if not _UUID.fullmatch(provider_id):
        raise ValueError(f"{provider} series IDs are UUIDs.")


def read_response[T](provider: str, response: httpx2.Response, parse: Callable[[object], T]) -> T:
    if response.status_code != 200:
        raise ProviderError(provider, response.status_code)
    try:
        return parse(response.json())
    except ValidationError as error:
        # Only where and what kind: the input values are the provider's body.
        problems = ", ".join(
            f"{'.'.join(str(part) for part in detail['loc'])} ({detail['type']})"
            for detail in error.errors()
        )
        logger.warning("%s sent a body Tomarr does not recognize: %s.", provider, problems)
        raise ProviderError(provider, response.status_code) from None
    except UNREADABLE as error:
        logger.warning("%s sent a body that is not JSON (%s).", provider, type(error).__name__)
        raise ProviderError(provider, response.status_code) from None


def require_base36(provider: str, provider_id: str) -> None:
    raise NotImplementedError
