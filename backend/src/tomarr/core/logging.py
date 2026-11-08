import json
import logging
import re
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

LOG_FILE_NAME = "tomarr.log"
MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# The bare name "key" is left out: it matches too much ordinary text ("sort key", "key=value").
CREDENTIAL_KEYS = ("apikey", "api_key", "token", "password", "authorization", "x-api-key")
REDACTED = "[redacted]"

_KEY = "|".join(re.escape(key) for key in CREDENTIAL_KEYS)
_QUERY_STRING = re.compile(r"""(?<=[\w/.~%-])\?[^\s"'<>#]+""")
_QUOTED_PAIR = re.compile(
    rf"""(?P<head>(?P<q>['"])(?:{_KEY})(?P=q)\s*:\s*(?P<vq>['"]))(?:\\.|(?!(?P=vq)).)*""",
    re.IGNORECASE,
)
_PAIR = re.compile(
    rf"""(?P<head>(?<![A-Za-z0-9])(?:{_KEY})\s*[:=]\s*['"]?(?:(?:bearer|basic|digest|token)\s+)?)"""
    r"""[^\s&,;'"]+""",
    re.IGNORECASE,
)
_RECORD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

_installed: list[logging.Handler] = []


def _extra_fields(record: logging.LogRecord) -> dict[str, object]:
    return {name: value for name, value in vars(record).items() if name not in _RECORD_ATTRS}


def _names_a_credential(name: str) -> bool:
    lowered = name.lower()
    return any(key in lowered for key in CREDENTIAL_KEYS)


class RedactionFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        text = _QUERY_STRING.sub(f"?{REDACTED}", text)
        text = _QUOTED_PAIR.sub(rf"\g<head>{REDACTED}", text)
        return _PAIR.sub(rf"\g<head>{REDACTED}", text)

    def redact_value(self, name: str, value: object) -> object:
        if _names_a_credential(name):
            return REDACTED
        if isinstance(value, str):
            return self.redact(value)
        if value is None or isinstance(value, int | float):
            return value
        if isinstance(value, Mapping):
            items = cast(Mapping[object, object], value).items()
            return {str(key): self.redact_value(str(key), item) for key, item in items}
        if isinstance(value, list | tuple | set | frozenset):
            return [self.redact_value("", item) for item in cast(Iterable[object], value)]
        return self.redact(str(value))

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            # A bad format call must not raise into the caller: stdlib logging only reports it
            # from inside emit, and filters run before emit.
            message = f"{record.msg} {record.args!r}"
        record.msg = self.redact(message)
        record.args = ()
        # Formatter.format reuses a cached exc_text, so the traceback has to be built and
        # redacted here, before any handler formats it.
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        for name, value in _extra_fields(record).items():
            setattr(record, name, self.redact_value(name, value))
        return True


class _JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created).astimezone()
        line: dict[str, object] = {
            "timestamp": created.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line["exception"] = record.exc_text
        for name, value in _extra_fields(record).items():
            line.setdefault(name, value)
        return json.dumps(line, default=str)


def configure_logging(level: str, log_dir: Path, secrets: Iterable[str]) -> None:
    close_logging()
    log_dir.mkdir(parents=True, exist_ok=True)
    redaction = RedactionFilter(secrets)
    formatter = _JsonLinesFormatter()
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            log_dir / LOG_FILE_NAME,
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
    ]
    root = logging.getLogger()
    for handler in handlers:
        handler.addFilter(redaction)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        _installed.append(handler)
    root.setLevel(level.upper())
    # uvicorn gives these loggers their own handlers and turns propagation off before the app
    # starts. Its access line carries the query string, so it has to reach the redacting handlers.
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.setLevel(logging.NOTSET)
        uvicorn_logger.propagate = True


def close_logging() -> None:
    root = logging.getLogger()
    for handler in _installed:
        root.removeHandler(handler)
        handler.close()
    _installed.clear()
