from tomarr.core.errors import (
    DomainError,
    ErrorCode,
    InvalidCredentials,
    NotAuthenticated,
    SetupAlreadyDone,
)


def all_subclasses(cls: type[DomainError]) -> set[type[DomainError]]:
    found: set[type[DomainError]] = set()
    for sub in cls.__subclasses__():
        found.add(sub)
        found |= all_subclasses(sub)
    return found


def test_error_codes_are_the_documented_set() -> None:
    assert {code.value for code in ErrorCode} == {
        "validation_failed",
        "not_authenticated",
        "invalid_credentials",
        "setup_already_done",
        "not_found",
        "method_not_allowed",
        "http_error",
        "internal_error",
    }


def test_every_domain_error_has_a_code_from_the_enum() -> None:
    subclasses = all_subclasses(DomainError)

    assert {SetupAlreadyDone, NotAuthenticated, InvalidCredentials} <= subclasses
    for error in subclasses:
        assert isinstance(error.code, ErrorCode)


def test_domain_errors_carry_their_own_code() -> None:
    assert SetupAlreadyDone.code is ErrorCode.SETUP_ALREADY_DONE
    assert NotAuthenticated.code is ErrorCode.NOT_AUTHENTICATED
    assert InvalidCredentials.code is ErrorCode.INVALID_CREDENTIALS
