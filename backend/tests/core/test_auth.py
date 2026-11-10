import hashlib
import time

import pytest
from itsdangerous import URLSafeTimedSerializer
from itsdangerous.encoding import base64_decode

from tomarr.core.auth import (
    DUMMY_HASH,
    SessionSigner,
    hash_password,
    is_local_address,
    session_fingerprint,
    verify_password,
)

PASSWORD = "correct horse battery staple"
NOW = 1_700_000_000.0
# The salt SessionSigner signs with. A forged token here only reaches the payload check when it
# matches, which test_the_forging_serializer_matches_the_signer proves.
SIGNER_SALT = "tomarr.session"


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
    is_argon2 = stored_hash.startswith("$argon2")
    leaked = PASSWORD in stored_hash
    assert is_argon2
    assert not leaked


def test_hashing_twice_gives_different_hashes(stored_hash: str) -> None:
    differ = hash_password(PASSWORD) != stored_hash
    assert differ


def test_verify_password_accepts_only_the_right_password(stored_hash: str) -> None:
    right = verify_password(PASSWORD, stored_hash)
    wrong = verify_password("wrong password", stored_hash)
    empty = verify_password("", stored_hash)
    assert right
    assert not wrong
    assert not empty


def test_dummy_hash_is_a_valid_hash_that_matches_nothing() -> None:
    is_argon2 = DUMMY_HASH.startswith("$argon2")
    matches_password = verify_password(PASSWORD, DUMMY_HASH)
    matches_empty = verify_password("", DUMMY_HASH)
    assert is_argon2
    assert not matches_password
    assert not matches_empty


def test_session_fingerprint_is_a_full_sha256_hex_digest(stored_hash: str) -> None:
    fingerprint = session_fingerprint("secret-a", "alice", stored_hash)

    is_sha256_hex = len(fingerprint) == 64 and set(fingerprint) <= set("0123456789abcdef")
    assert is_sha256_hex


def test_session_fingerprint_is_stable_for_the_same_inputs(stored_hash: str) -> None:
    first = session_fingerprint("secret-a", "alice", stored_hash)

    stable = first == session_fingerprint("secret-a", "alice", stored_hash)
    assert stable


def test_session_fingerprint_changes_with_each_input(stored_hash: str) -> None:
    base = session_fingerprint("secret-a", "alice", stored_hash)

    other_secret = session_fingerprint("secret-b", "alice", stored_hash) != base
    other_username = session_fingerprint("secret-a", "bob", stored_hash) != base
    other_hash = session_fingerprint("secret-a", "alice", hash_password(PASSWORD)) != base
    assert other_secret
    assert other_username
    assert other_hash


def test_session_fingerprint_separates_the_username_from_the_hash() -> None:
    # Without a separator these two would hash the same bytes.
    separated = session_fingerprint("s", "ab", "c") != session_fingerprint("s", "a", "bc")
    assert separated


def test_session_token_payload_does_not_reveal_the_username_or_the_hash(
    stored_hash: str,
) -> None:
    username = "alice"
    token = SessionSigner("secret-a").issue(session_fingerprint("secret-a", username, stored_hash))

    decoded = base64_decode(token.split(".")[0]).decode()

    old_scheme_fingerprint = hashlib.sha256(stored_hash.encode()).hexdigest()[:16]
    hash_pieces = [stored_hash[i : i + 16] for i in range(len(stored_hash) - 15)]
    leaked = (
        username in decoded
        or old_scheme_fingerprint in decoded
        or any(piece in decoded for piece in hash_pieces)
    )
    assert not leaked


def test_session_round_trip_returns_the_fingerprint() -> None:
    signer = SessionSigner("secret-a")
    token = signer.issue("abc123")

    matches = signer.read(token, max_age=60) == "abc123"
    assert matches


def test_session_with_tampered_payload_is_rejected() -> None:
    signer = SessionSigner("secret-a")
    token = signer.issue("abc123")
    flipped = "B" if token[0] == "A" else "A"

    rejected = signer.read(flipped + token[1:], max_age=60) is None
    assert rejected


def test_session_signed_with_another_secret_is_rejected() -> None:
    token = SessionSigner("secret-b").issue("abc123")

    rejected = SessionSigner("secret-a").read(token, max_age=60) is None
    assert rejected


def test_session_older_than_max_age_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    signer = SessionSigner("secret-a")
    monkeypatch.setattr(time, "time", lambda: NOW)
    token = signer.issue("abc123")

    monkeypatch.setattr(time, "time", lambda: NOW + 59)
    still_valid = signer.read(token, max_age=60) == "abc123"
    assert still_valid

    monkeypatch.setattr(time, "time", lambda: NOW + 61)
    rejected = signer.read(token, max_age=60) is None
    assert rejected


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "....", "éè"])
def test_garbage_session_token_is_rejected(token: str) -> None:
    rejected = SessionSigner("secret-a").read(token, max_age=60) is None
    assert rejected


def test_the_forging_serializer_matches_the_signer() -> None:
    forger = URLSafeTimedSerializer("secret-a", salt=SIGNER_SALT)

    read_back = SessionSigner("secret-a").read(forger.dumps("abc123"), max_age=60) == "abc123"
    assert read_back


@pytest.mark.parametrize(
    "payload",
    [{"fingerprint": "abc123"}, ["abc123"], ["alice", "abc123"], 7, None],
    ids=["dict", "list", "pair", "number", "null"],
)
def test_a_correctly_signed_payload_that_is_not_one_string_is_rejected(payload: object) -> None:
    forged = URLSafeTimedSerializer("secret-a", salt=SIGNER_SALT).dumps(payload)

    rejected = SessionSigner("secret-a").read(forged, max_age=60) is None
    assert rejected
