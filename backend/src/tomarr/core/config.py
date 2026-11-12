import os
import re
import secrets
import tomllib
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

CONFIG_FILE_NAME = "config.toml"
API_KEY_ENV = "TOMARR__AUTH__APIKEY"

LogLevel = Literal["debug", "info", "warning", "error", "critical"]

_URL_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")


class Server(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bindaddress: str = "0.0.0.0"
    port: int = Field(default=6464, ge=1, le=65535)
    urlbase: str = ""

    @field_validator("urlbase")
    @classmethod
    def _normalise_urlbase(cls, value: str) -> str:
        segment = value.strip("/")
        if not segment:
            return ""
        if not _URL_SEGMENT.fullmatch(segment):
            raise ValueError("urlbase must be a single path segment such as /tomarr")
        return f"/{segment}"


class Auth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apikey: str = Field(min_length=1)


class Log(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: LogLevel = "info"

    @field_validator("level", mode="before")
    @classmethod
    def _lower_case_level(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value


class Settings(BaseSettings):
    # Validation errors reach the startup traceback, and the input may be the API key.
    model_config = SettingsConfigDict(
        env_prefix="TOMARR__", env_nested_delimiter="__", hide_input_in_errors=True
    )

    server: Server = Server()
    # Validating the empty default makes a missing key fail as auth.apikey, not as auth.
    auth: Auth = Field(default_factory=dict, validate_default=True)
    log: Log = Log()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))


def config_dir() -> Path:
    # The container always uses /config, so users only change the host side of the mount.
    # TOMARR_CONFIG_DIR exists so tests and local runs can avoid writing to /config.
    # An empty value counts as unset, since Path("") is the working directory.
    return Path(os.environ.get("TOMARR_CONFIG_DIR") or "/config")


def static_dir() -> Path:
    # TOMARR_STATIC_DIR points the image at the build it ships. The default is the checkout's
    # build, so a local run serves what `pnpm build` wrote. An empty value counts as unset, since
    # Path("") is the working directory.
    default = Path(__file__).parents[4] / "frontend" / "dist"
    return Path(os.environ.get("TOMARR_STATIC_DIR") or default)


def load_settings(config_dir: Path) -> Settings:
    path = config_dir / CONFIG_FILE_NAME
    if not path.exists():
        # A key given through the environment is not copied to disk.
        key_from_env = any(name.upper() == API_KEY_ENV for name in os.environ)
        _write_first_run_file(path, with_api_key=not key_from_env)

    class _FileSettings(Settings):
        model_config = SettingsConfigDict(toml_file=path)

    try:
        # The sources fill every field, which pyright cannot see from the signature.
        return _FileSettings()  # pyright: ignore[reportCallIssue]
    except tomllib.TOMLDecodeError as error:
        # tomllib messages give a line and column but not the text, and the file holds the API key.
        raise ValueError(f"{path} is not valid TOML: {error}") from None


def _write_first_run_file(path: Path, *, with_api_key: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    defaults: dict[str, dict[str, object]] = {"server": Server().model_dump()}
    if with_api_key:
        defaults["auth"] = {"apikey": secrets.token_urlsafe(32)}
    defaults["log"] = Log().model_dump()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        tomli_w.dump(defaults, file)
