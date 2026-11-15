from typing import TypedDict

REQUEST_HEADER_NAMES = ["authorization", "x-api-key", "x-goog-api-key", "cookie"]
RESPONSE_HEADER_NAMES = ["set-cookie"]
PARAM_NAMES = ["apikey", "api_key", "key", "token", "username", "password"]
PLACEHOLDER = "REDACTED"


class Response(TypedDict):
    status: dict[str, object]
    headers: dict[str, str | list[str]]
    body: dict[str, object]


def redact_response_headers(response: Response) -> Response:
    """A vcrpy before_record_response hook. vcrpy's own header filters only touch requests.
    The value keeps its shape, since replay iterates a list of values."""
    headers = response["headers"]
    for name, value in headers.items():
        if name.lower() in RESPONSE_HEADER_NAMES:
            headers[name] = [PLACEHOLDER] * len(value) if isinstance(value, list) else PLACEHOLDER
    return response
