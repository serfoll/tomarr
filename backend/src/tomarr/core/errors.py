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
    RATE_LIMITED = "rate_limited"


class DomainError(Exception):
    code: ErrorCode


class SetupAlreadyDone(DomainError):
    code = ErrorCode.SETUP_ALREADY_DONE


class NotAuthenticated(DomainError):
    code = ErrorCode.NOT_AUTHENTICATED


class InvalidCredentials(DomainError):
    code = ErrorCode.INVALID_CREDENTIALS


class RateLimited(DomainError):
    code = ErrorCode.RATE_LIMITED

    def __init__(self, service: str, retry_after: float | None) -> None:
        super().__init__(service, retry_after)
        self.service = service
        self.retry_after = retry_after
