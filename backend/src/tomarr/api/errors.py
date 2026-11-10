import logging
from collections.abc import Mapping
from typing import NamedTuple

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from tomarr.api.request_id import REQUEST_ID_HEADER
from tomarr.core.errors import DomainError, ErrorCode

logger = logging.getLogger(__name__)


class ErrorKind(NamedTuple):
    status: int
    message: str


ERRORS: dict[ErrorCode, ErrorKind] = {
    ErrorCode.VALIDATION_FAILED: ErrorKind(
        status.HTTP_400_BAD_REQUEST, "The request has missing or invalid fields."
    ),
    ErrorCode.NOT_AUTHENTICATED: ErrorKind(
        status.HTTP_401_UNAUTHORIZED, "Not logged in. Log in or send a valid API key."
    ),
    ErrorCode.INVALID_CREDENTIALS: ErrorKind(
        status.HTTP_401_UNAUTHORIZED, "Wrong username or password."
    ),
    ErrorCode.SETUP_ALREADY_DONE: ErrorKind(
        status.HTTP_409_CONFLICT, "Setup is already done. Log in instead."
    ),
    ErrorCode.NOT_FOUND: ErrorKind(status.HTTP_404_NOT_FOUND, "Nothing exists at this address."),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorKind(
        status.HTTP_405_METHOD_NOT_ALLOWED, "This address does not accept that method."
    ),
    # The response keeps the status of the HTTPException; this one only stands in for the table.
    ErrorCode.HTTP_ERROR: ErrorKind(
        status.HTTP_400_BAD_REQUEST, "The request could not be served."
    ),
    ErrorCode.INTERNAL_ERROR: ErrorKind(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Something went wrong on the server. The log has the details under this request ID.",
    ),
}
_HTTP_CODES = {
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
}
_HEADERS = {ErrorCode.NOT_AUTHENTICATED: {"WWW-Authenticate": "APIKey"}}
_VALIDATION_RESPONSE = {
    "description": "Missing or invalid fields.",
    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
}


class ErrorResponse(BaseModel):
    code: ErrorCode
    message: str
    request_id: str


def install_error_handlers(app: FastAPI) -> None:
    app.exception_handler(DomainError)(_handle_domain_error)
    app.exception_handler(RequestValidationError)(_handle_validation_error)
    app.exception_handler(HTTPException)(_handle_http_exception)
    app.exception_handler(Exception)(_handle_unexpected_error)


def _error_response(
    request: Request,
    code: ErrorCode,
    status_code: int | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    kind = ERRORS[code]
    body = ErrorResponse(code=code, message=kind.message, request_id=_request_id(request))
    return JSONResponse(body.model_dump(mode="json"), status_code or kind.status, headers)


def _request_id(request: Request) -> str:
    request_id: str = request.state.request_id
    return request_id


async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return _error_response(request, exc.code, headers=_HEADERS.get(exc.code))


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic puts the submitted value in "input" and sometimes in "ctx", so only these two go.
    fields = [{"loc": list(error["loc"]), "type": error["type"]} for error in exc.errors()]
    logger.info("Request validation failed", extra={"errors": fields})
    return _error_response(request, ErrorCode.VALIDATION_FAILED)


async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, ErrorCode.HTTP_ERROR)
    return _error_response(request, code, exc.status_code, exc.headers)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Starlette calls this handler from its outermost middleware, after the request ID middleware
    # has reset the context variable and stopped adding the header, so both are done here.
    request_id = _request_id(request)
    logger.error("Unexpected error", exc_info=exc, extra={"request_id": request_id})
    return _error_response(
        request, ErrorCode.INTERNAL_ERROR, headers={REQUEST_ID_HEADER: request_id}
    )


def document_error_responses(app: FastAPI) -> None:
    # FastAPI writes a 422 HTTPValidationError entry on every route that takes input and has no
    # setting to change it, so the generated document is rewritten to the 400 this app sends.
    generate = app.openapi

    def openapi() -> dict[str, object]:
        schema = generate()
        for operations in schema["paths"].values():
            for operation in operations.values():
                responses = operation["responses"]
                if "422" in responses:
                    del responses["422"]
                    responses["400"] = _VALIDATION_RESPONSE
        for name in ("HTTPValidationError", "ValidationError"):
            schema["components"]["schemas"].pop(name, None)
        return schema

    app.openapi = openapi
