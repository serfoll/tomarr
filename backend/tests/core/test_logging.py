import copy
import json
import logging
import logging.config
import logging.handlers
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from uvicorn.config import LOGGING_CONFIG

from tomarr.core import logging as tomarr_logging
from tomarr.core.logging import close_logging, configure_logging

SECRET = "abc123"
LITERAL_SECRET = "Zq9vLx2Pw"
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

logger = logging.getLogger("tomarr.test")


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    root_level = root.level
    saved = {
        name: (lg.level, lg.propagate, list(lg.handlers))
        for name in UVICORN_LOGGERS
        for lg in [logging.getLogger(name)]
    }
    yield
    close_logging()
    root.setLevel(root_level)
    for name, (level, propagate, handlers) in saved.items():
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = propagate
        lg.handlers[:] = handlers


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs"


def configure(log_dir: Path) -> None:
    configure_logging("info", log_dir, [LITERAL_SECRET])


def outputs(capsys: pytest.CaptureFixture[str], log_dir: Path) -> list[str]:
    return [capsys.readouterr().out, (log_dir / "tomarr.log").read_text(encoding="utf-8")]


def json_lines(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.splitlines()]


@pytest.mark.parametrize(
    ("message", "args"),
    [
        ("Searching with api_key=abc123", ()),
        ("Fetching https://x.test/p?apikey=abc123&q=1", ()),
        ("Fetching %s", ("https://x.test/p?q=1&token=abc123",)),
        ("Login with %s", ("password=abc123",)),
        ('Response body {"token": "abc123", "id": 7}', ()),
        ("Request headers: %s", ({"Authorization": "Bearer abc123"},)),
        ("Request headers: %s", ({"X-Api-Key": "abc123"},)),
        ("Sent Authorization: Bearer abc123 to the indexer", ()),
        ("Sent X-Api-Key: abc123 to the indexer", ()),
        ("Sent Authorization: Negotiate abc123 to the proxy", ()),
        ("Sending x-goog-api-key: abc123", ()),
        ("Request headers: %s", ({"x-goog-api-key": "abc123"},)),
        ("Request api-key=abc123 cookie=abc123", ()),
        ("Token exchange with client_secret=abc123", ()),
    ],
)
def test_credentials_in_the_message_are_redacted(
    capsys: pytest.CaptureFixture[str],
    log_dir: Path,
    message: str,
    args: tuple[object, ...],
) -> None:
    configure(log_dir)

    logger.info(message, *args)

    for text in outputs(capsys, log_dir):
        assert SECRET not in text
        assert "[redacted]" in text


def test_query_string_is_replaced_whole(capsys: pytest.CaptureFixture[str], log_dir: Path) -> None:
    configure(log_dir)

    logger.info("Fetching https://x.test/p?apikey=abc123&q=1 done")

    for text in outputs(capsys, log_dir):
        assert json_lines(text)[0]["message"] == "Fetching https://x.test/p?[redacted] done"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('Login with password="my abc123 phrase" done', 'Login with password="[redacted]" done'),
        ("Login with password='my abc123 phrase", "Login with password='[redacted]"),
        (
            "Connecting to http://admin:abc123@qbit.local:8080/api",
            "Connecting to http://admin:[redacted]@qbit.local:8080/api",
        ),
    ],
)
def test_credential_value_is_replaced_whole(
    capsys: pytest.CaptureFixture[str], log_dir: Path, message: str, expected: str
) -> None:
    configure(log_dir)

    logger.info(message)

    for text in outputs(capsys, log_dir):
        assert json_lines(text)[0]["message"] == expected


def test_credential_in_an_extra_field_is_redacted(
    capsys: pytest.CaptureFixture[str], log_dir: Path
) -> None:
    configure(log_dir)

    logger.info("Fetched", extra={"url": "https://x.test/p?apikey=abc123", "api_key": SECRET})

    for text in outputs(capsys, log_dir):
        assert SECRET not in text
        line = json_lines(text)[0]
        assert line["url"] == "https://x.test/p?[redacted]"
        assert line["api_key"] == "[redacted]"


class UrlLike:
    def __str__(self) -> str:
        return "https://x.test/p?apikey=abc123"


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        (
            {"headers": {"Authorization": "Bearer abc123", "Accept": "application/json"}},
            {"headers": {"Authorization": "[redacted]", "Accept": "application/json"}},
        ),
        ({"url": UrlLike()}, {"url": "https://x.test/p?[redacted]"}),
        ({"access_token": SECRET}, {"access_token": "[redacted]"}),
        ({"client_secret": SECRET}, {"client_secret": "[redacted]"}),
        ({"x_api_key": SECRET}, {"x_api_key": "[redacted]"}),
        ({"headers": {"x-goog-api-key": SECRET}}, {"headers": {"x-goog-api-key": "[redacted]"}}),
        ({"headers": {"Set-Cookie": SECRET}}, {"headers": {"Set-Cookie": "[redacted]"}}),
        ({"urls": ["https://x.test/p?token=abc123"]}, {"urls": ["https://x.test/p?[redacted]"]}),
    ],
)
def test_credential_in_a_structured_extra_is_redacted(
    capsys: pytest.CaptureFixture[str],
    log_dir: Path,
    extra: dict[str, object],
    expected: dict[str, object],
) -> None:
    configure(log_dir)

    logger.info("Fetched", extra=extra)

    for text in outputs(capsys, log_dir):
        assert SECRET not in text
        line = json_lines(text)[0]
        for name, value in expected.items():
            assert line[name] == value


class RaisesOnStr:
    def __str__(self) -> str:
        raise RuntimeError("cannot render")


@pytest.mark.parametrize(
    ("msg", "args", "prefix"),
    [
        ("Fetching %s from %s", (f"token={SECRET}",), "Fetching %s from %s"),
        ("Fetching %(a)s with %(b)s", ({"a": f"token={SECRET}"},), "Fetching %(a)s with %(b)s"),
        ("Fetching %s", (RaisesOnStr(),), "Fetching %s"),
    ],
)
def test_bad_format_args_do_not_raise_and_are_redacted(
    capsys: pytest.CaptureFixture[str],
    log_dir: Path,
    msg: str,
    args: tuple[object, ...],
    prefix: str,
) -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    configure(log_dir)
    record = logger.makeRecord(logger.name, logging.INFO, __file__, 1, msg, args, None)

    # pytest's own capture handler on root re-raises format errors, so only ours are driven.
    for handler in root.handlers:
        if handler not in before:
            handler.handle(record)

    for text in outputs(capsys, log_dir):
        assert SECRET not in text
        message = json_lines(text)[0]["message"]
        assert isinstance(message, str)
        assert message.startswith(prefix)


def test_credential_in_a_traceback_is_redacted(
    capsys: pytest.CaptureFixture[str], log_dir: Path
) -> None:
    configure(log_dir)

    try:
        raise ValueError(f"indexer rejected token={SECRET}")
    except ValueError:
        logger.exception("Search failed")

    for text in outputs(capsys, log_dir):
        assert SECRET not in text
        line = json_lines(text)[0]
        assert isinstance(line["exception"], str)
        assert "ValueError: indexer rejected token=[redacted]" in line["exception"]


def test_literal_secret_is_redacted_anywhere(
    capsys: pytest.CaptureFixture[str], log_dir: Path
) -> None:
    configure(log_dir)

    logger.info("Loaded key %s", LITERAL_SECRET, extra={"note": f"key is {LITERAL_SECRET}"})

    for text in outputs(capsys, log_dir):
        assert LITERAL_SECRET not in text
        line = json_lines(text)[0]
        assert line["message"] == "Loaded key [redacted]"
        assert line["note"] == "key is [redacted]"


LONG = 100_000


@pytest.mark.parametrize(
    "text",
    [
        "a1" * (LONG // 2),
        "GET /" + "a" * LONG + " HTTP/1.1",
        "a.-+" * (LONG // 4),
        '"' * LONG,
        "'" * LONG,
        "a" + "?" * LONG,
        "token=" * (LONG // 6),
        'password="' + "x" * LONG,
        "http://" + "h" * LONG,
        "http://" + "u" * LONG + ":" + "p" * LONG,
    ],
    ids=[
        "alnum-run",
        "long-request-path",
        "dot-dash-plus-run",
        "double-quotes",
        "single-quotes",
        "question-marks",
        "token-repeats",
        "unterminated-quoted-value",
        "long-host",
        "userinfo-without-at",
    ],
)
def test_redaction_stays_fast_on_long_input(text: str) -> None:
    redaction = tomarr_logging.RedactionFilter([])

    started = time.perf_counter()
    redaction.redact(text)

    assert time.perf_counter() - started < 0.5


def test_ordinary_lines_are_json_and_unchanged(
    capsys: pytest.CaptureFixture[str], log_dir: Path
) -> None:
    configure(log_dir)

    logger.warning(
        "Imported %s volume %d",
        "鬼滅の刃",
        3,
        extra={"series_id": 42, "title": "Vol 3", "input_tokens": 1234, "tokens_used": 56},
    )

    for text in outputs(capsys, log_dir):
        assert "鬼滅の刃" in text
        [line] = json_lines(text)
        assert isinstance(line["timestamp"], str)
        assert line["level"] == "WARNING"
        assert line["logger"] == "tomarr.test"
        assert line["message"] == "Imported 鬼滅の刃 volume 3"
        assert line["series_id"] == 42
        assert line["title"] == "Vol 3"
        assert line["input_tokens"] == 1234
        assert line["tokens_used"] == 56


@pytest.fixture
def paris_tz(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.usefixtures("paris_tz")
@pytest.mark.parametrize(
    ("created", "expected"),
    [
        (datetime(2026, 1, 15, 12, 0, tzinfo=UTC), "2026-01-15T13:00:00.000+01:00"),
        (datetime(2026, 7, 15, 12, 0, tzinfo=UTC), "2026-07-15T14:00:00.000+02:00"),
    ],
)
def test_timestamp_is_local_time_with_offset(
    capsys: pytest.CaptureFixture[str], log_dir: Path, created: datetime, expected: str
) -> None:
    configure(log_dir)
    record = logger.makeRecord(logger.name, logging.INFO, __file__, 1, "Tick", (), None)
    record.created = created.timestamp()

    logger.handle(record)

    for text in outputs(capsys, log_dir):
        assert json_lines(text)[0]["timestamp"] == expected


def test_uvicorn_access_lines_are_redacted(
    capsys: pytest.CaptureFixture[str], log_dir: Path
) -> None:
    logging.config.dictConfig(copy.deepcopy(LOGGING_CONFIG))
    configure(log_dir)

    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1:50000",
        "GET",
        "/api/v1/series?token=abc123",
        "1.1",
        200,
    )

    for text in outputs(capsys, log_dir):
        assert SECRET not in text
        line = json_lines(text)[0]
        assert line["logger"] == "uvicorn.access"
        assert line["message"] == '127.0.0.1:50000 - "GET /api/v1/series?[redacted] HTTP/1.1" 200'


def test_file_rotates_and_keeps_five_backups(
    monkeypatch: pytest.MonkeyPatch, log_dir: Path
) -> None:
    monkeypatch.setattr(tomarr_logging, "MAX_LOG_BYTES", 200)
    configure(log_dir)

    for number in range(100):
        logger.info("Line %d of the rotation test", number)

    backups = sorted(path.name for path in log_dir.glob("tomarr.log.*"))
    assert backups == [f"tomarr.log.{n}" for n in range(1, 6)]


def test_configuring_twice_leaves_two_handlers(log_dir: Path) -> None:
    root = logging.getLogger()
    before = list(root.handlers)

    configure(log_dir)
    configure(log_dir)

    added = [handler for handler in root.handlers if handler not in before]
    assert len(added) == 2
    assert sum(isinstance(h, logging.handlers.RotatingFileHandler) for h in added) == 1
