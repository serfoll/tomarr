import os
import re
import stat
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from tomarr.core.config import Auth, Log, Server, config_dir, load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("TOMARR"):
            monkeypatch.delenv(name)


def test_first_run_writes_defaults_and_a_private_key(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "config")

    path = tmp_path / "config" / "config.toml"
    written = tomllib.loads(path.read_text())
    assert written == {
        "server": {"bindaddress": "0.0.0.0", "port": 6464, "urlbase": ""},
        "auth": {"apikey": settings.auth.apikey},
        "log": {"level": "info"},
    }
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", settings.auth.apikey)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_second_load_keeps_the_key_and_does_not_rewrite_the_file(tmp_path: Path) -> None:
    first = load_settings(tmp_path)
    path = tmp_path / "config.toml"
    before = (path.read_bytes(), path.stat().st_mtime_ns)

    second = load_settings(tmp_path)

    assert second.auth.apikey == first.auth.apikey
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_env_overrides_one_field_and_leaves_the_rest_from_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.toml").write_text(
        '[server]\nbindaddress = "127.0.0.1"\nport = 7000\nurlbase = "/tomarr"\n'
        '[auth]\napikey = "from-file"\n[log]\nlevel = "debug"\n'
    )
    monkeypatch.setenv("TOMARR__SERVER__PORT", "9000")

    settings = load_settings(tmp_path)

    assert settings.server.port == 9000
    assert settings.server.bindaddress == "127.0.0.1"
    assert settings.server.urlbase == "/tomarr"
    assert settings.auth.apikey == "from-file"
    assert settings.log.level == "debug"


def test_env_api_key_on_first_run_wins_but_the_file_keeps_the_generated_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOMARR__AUTH__APIKEY", "from-env")

    settings = load_settings(tmp_path)

    written = tomllib.loads((tmp_path / "config.toml").read_text())
    assert settings.auth.apikey == "from-env"
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", written["auth"]["apikey"])


def test_config_dir_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOMARR_CONFIG_DIR", str(tmp_path))

    assert config_dir() == tmp_path


def test_config_dir_defaults_to_slash_config() -> None:
    assert config_dir() == Path("/config")


@pytest.mark.parametrize("port", [0, 65536])
def test_port_outside_1_to_65535_is_rejected(port: int) -> None:
    with pytest.raises(ValidationError):
        Server(port=port)


@pytest.mark.parametrize("port", [1, 65535])
def test_port_bounds_are_accepted(port: int) -> None:
    assert Server(port=port).port == port


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Log(level="verbose")  # pyright: ignore[reportArgumentType]


def test_log_level_is_stored_lower_case() -> None:
    assert Log(level="INFO").level == "info"  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("urlbase", ["tomarr/", "/tomarr/", "/tomarr", "tomarr"])
def test_urlbase_normalises_to_a_leading_slash_segment(urlbase: str) -> None:
    assert Server(urlbase=urlbase).urlbase == "/tomarr"


@pytest.mark.parametrize("urlbase", ["", "/", "//"])
def test_empty_urlbase_normalises_to_empty_string(urlbase: str) -> None:
    assert Server(urlbase=urlbase).urlbase == ""


@pytest.mark.parametrize("urlbase", ["a b", "a?b", "a#b", "a/b", "a//b", "https://x"])
def test_bad_urlbase_is_rejected(urlbase: str) -> None:
    with pytest.raises(ValidationError):
        Server(urlbase=urlbase)


def test_malformed_file_error_names_the_file_and_hides_its_content(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[auth]\napikey = "super-secret-value" oops\n')

    with pytest.raises(ValueError, match=re.escape(str(path))) as excinfo:
        load_settings(tmp_path)

    assert "line 2" in str(excinfo.value)
    assert "super-secret-value" not in str(excinfo.value)


def test_invalid_value_in_the_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text('[auth]\napikey = "k"\n[server]\nport = 0\n')

    with pytest.raises(ValidationError):
        load_settings(tmp_path)


def test_auth_requires_an_api_key() -> None:
    with pytest.raises(ValidationError):
        Auth()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize(
    ("section", "name"),
    [("server", "bind_address"), ("server", "url_base"), ("auth", "api_key"), ("log", "lvl")],
)
def test_unknown_key_in_the_file_is_rejected(tmp_path: Path, section: str, name: str) -> None:
    sections = {"server": "", "auth": 'apikey = "k"\n', "log": ""}
    sections[section] += f'{name} = "x"\n'
    (tmp_path / "config.toml").write_text(
        "".join(f"[{title}]\n{body}" for title, body in sections.items())
    )

    with pytest.raises(ValidationError, match=re.escape(f"{section}.{name}")):
        load_settings(tmp_path)


def test_unknown_key_in_the_environment_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOMARR__SERVER__URL_BASE", "/x")

    with pytest.raises(ValidationError, match=re.escape("server.url_base")):
        load_settings(tmp_path)


def test_validation_error_names_the_field_and_hides_the_value(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text("[auth]\napikey = 123456789012\n")

    with pytest.raises(ValidationError, match=re.escape("auth.apikey")) as excinfo:
        load_settings(tmp_path)

    assert "123456789012" not in str(excinfo.value)
