from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "validation_failed"
    NOT_AUTHENTICATED = "not_authenticated"
    INVALID_CREDENTIALS = "invalid_credentials"
    SETUP_ALREADY_DONE = "setup_already_done"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    HTTP_ERROR = "http_error"
    INTERNAL_ERROR = "internal_error"


class DomainError(Exception):
    code: ErrorCode


class SetupAlreadyDone(DomainError):
    code = ErrorCode.SETUP_ALREADY_DONE


class NotAuthenticated(DomainError):
    code = ErrorCode.NOT_AUTHENTICATED


class InvalidCredentials(DomainError):
    code = ErrorCode.INVALID_CREDENTIALS
