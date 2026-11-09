import time

import pytest

from tomarr.core.auth import (
    DUMMY_HASH,
    SessionPayload,
    SessionSigner,
    hash_password,
    is_local_address,
    password_fingerprint,
    verify_password,
)

PASSWORD = "correct horse battery staple"
NOW = 1_700_000_000.0


@pytest.fixture(scope="module")
def stored_hash() -> str:
    return hash_password(PASSWORD)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.5",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.5",
        "169.254.1.1",
        "fe80::1",
        "fd00::1",
        "::ffff:192.168.1.5",
        "::ffff:127.0.0.1",
    ],
)
def test_local_addresses_are_local(host: str) -> None:
    assert is_local_address(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "8.8.8.8",
        "172.32.0.1",
        "100.64.0.1",
        "2001:db8::1",
        "::ffff:8.8.8.8",
        "",
        "testclient",
        "not-an-ip",
        None,
    ],
)
def test_other_hosts_are_not_local(host: str | None) -> None:
    assert is_local_address(host) is False


def test_hash_password_is_argon2_and_hides_the_password(stored_hash: str) -> None:
    assert stored_hash.startswith("$argon2")
    assert PASSWORD not in stored_hash


def test_hashing_twice_gives_different_hashes(stored_hash: str) -> None:
    assert hash_password(PASSWORD) != stored_hash


def test_verify_password_accepts_only_the_right_password(stored_hash: str) -> None:
    assert verify_password(PASSWORD, stored_hash) is True
    assert verify_password("wrong password", stored_hash) is False
    assert verify_password("", stored_hash) is False


def test_dummy_hash_is_a_valid_hash_that_matches_nothing() -> None:
    assert DUMMY_HASH.startswith("$argon2")
    assert verify_password(PASSWORD, DUMMY_HASH) is False
    assert verify_password("", DUMMY_HASH) is False


def test_password_fingerprint_is_stable_per_hash_and_differs_between_hashes(
    stored_hash: str,
) -> None:
    other_hash = hash_password(PASSWORD)
    fingerprint = password_fingerprint(stored_hash)
    assert fingerprint == password_fingerprint(stored_hash)
    assert len(fingerprint) == 16
    assert fingerprint != password_fingerprint(other_hash)


def test_session_round_trip_returns_username_and_fingerprint() -> None:
    signer = SessionSigner("secret-a")
    token = signer.issue("alice", "abc123")
    assert signer.read(token, max_age=60) == SessionPayload("alice", "abc123")


def test_session_with_tampered_payload_is_rejected() -> None:
    signer = SessionSigner("secret-a")
    token = signer.issue("alice", "abc123")
    flipped = "B" if token[0] == "A" else "A"
    assert signer.read(flipped + token[1:], max_age=60) is None


def test_session_signed_with_another_secret_is_rejected() -> None:
    token = SessionSigner("secret-b").issue("alice", "abc123")
    assert SessionSigner("secret-a").read(token, max_age=60) is None


def test_session_older_than_max_age_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    signer = SessionSigner("secret-a")
    monkeypatch.setattr(time, "time", lambda: NOW)
    token = signer.issue("alice", "abc123")

    monkeypatch.setattr(time, "time", lambda: NOW + 59)
    assert signer.read(token, max_age=60) == SessionPayload("alice", "abc123")

    monkeypatch.setattr(time, "time", lambda: NOW + 61)
    assert signer.read(token, max_age=60) is None


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "....", "éè"])
def test_garbage_session_token_is_rejected(token: str) -> None:
    assert SessionSigner("secret-a").read(token, max_age=60) is None
