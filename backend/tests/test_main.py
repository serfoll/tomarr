import socket
import threading
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import uvicorn
from pydantic import ValidationError

from tomarr import __main__ as entry
from tomarr.__main__ import main

HEALTH_PATH = "/api/v1/system/health"
API_KEY = "secret-key-for-the-test"

# The healthcheck tests talk to servers on this machine only.
pytestmark = pytest.mark.block_network(allowed_hosts=["127.0.0.1", "::1"])


def write_config(directory: Path, *, bindaddress: str = "127.0.0.1", port: object = 7000) -> Path:
    path = directory / "config.toml"
    path.write_text(
        f'[server]\nbindaddress = "{bindaddress}"\nport = {port}\n[auth]\napikey = "{API_KEY}"\n'
    )
    return path


class UvicornCalls:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


@pytest.fixture
def uvicorn_run(monkeypatch: pytest.MonkeyPatch) -> UvicornCalls:
    recorder = UvicornCalls()
    monkeypatch.setattr(uvicorn, "run", recorder)
    return recorder


def test_main_serves_the_app_factory_on_the_configured_host_and_port(
    tmp_path: Path, uvicorn_run: UvicornCalls
) -> None:
    write_config(tmp_path, bindaddress="127.0.0.1", port=7000)

    assert main([]) == 0

    # No forwarded_allow_ips: uvicorn then reads FORWARDED_ALLOW_IPS and defaults to loopback.
    assert uvicorn_run.calls == [
        (
            ("tomarr.app:create_app",),
            {
                "factory": True,
                "host": "127.0.0.1",
                "port": 7000,
                "timeout_graceful_shutdown": 5,
                "proxy_headers": True,
            },
        )
    ]


def test_environment_overrides_the_file_for_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, uvicorn_run: UvicornCalls
) -> None:
    write_config(tmp_path, bindaddress="127.0.0.1", port=7000)
    monkeypatch.setenv("TOMARR__SERVER__PORT", "9100")
    monkeypatch.setenv("TOMARR__SERVER__BINDADDRESS", "::1")

    main([])

    kwargs = uvicorn_run.calls[0][1]
    assert (kwargs["host"], kwargs["port"]) == ("::1", 9100)


def test_first_run_writes_the_config_file_and_serves_the_defaults(
    tmp_path: Path, uvicorn_run: UvicornCalls
) -> None:
    main([])

    assert (tmp_path / "config.toml").is_file()
    kwargs = uvicorn_run.calls[0][1]
    assert (kwargs["host"], kwargs["port"]) == ("0.0.0.0", 6464)


def test_an_invalid_port_stops_with_the_settings_error_and_does_not_start_uvicorn(
    tmp_path: Path, uvicorn_run: UvicornCalls
) -> None:
    write_config(tmp_path, port=70000)

    with pytest.raises(ValidationError) as error:
        main([])

    assert "server.port" in str(error.value)
    assert API_KEY not in str(error.value)
    assert uvicorn_run.calls == []


def test_invalid_toml_stops_without_echoing_the_file_and_does_not_start_uvicorn(
    tmp_path: Path, uvicorn_run: UvicornCalls
) -> None:
    (tmp_path / "config.toml").write_text(f'[auth]\napikey = "{API_KEY}\n')

    with pytest.raises(ValueError, match="is not valid TOML") as error:
        main([])

    assert API_KEY not in str(error.value)
    assert uvicorn_run.calls == []


def test_an_unknown_command_exits_with_a_usage_message(uvicorn_run: UvicornCalls) -> None:
    with pytest.raises(SystemExit, match="Unknown command 'nope'"):
        main(["nope"])

    assert uvicorn_run.calls == []


class HealthHandler(BaseHTTPRequestHandler):
    status = 200
    location: str | None = None

    def do_GET(self) -> None:
        if self.path != HEALTH_PATH:
            self.send_error(404)
            return
        self.send_response(self.status)
        if self.location is not None:
            self.send_header("Location", self.location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


@contextmanager
def health_server(
    *, host: str = "127.0.0.1", status: int = 200, location: str | None = None
) -> Iterator[int]:
    handler = type("Handler", (HealthHandler,), {"status": status, "location": location})
    server_class = ThreadingHTTPServer
    if ":" in host:
        server_class = type("Server6", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    server = server_class((host, 0), handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@contextmanager
def silent_server() -> Iterator[int]:
    """Accepts connections and never answers."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    accepted: list[socket.socket] = []
    stop = threading.Event()

    def accept_loop() -> None:
        listener.settimeout(0.1)
        while not stop.is_set():
            try:
                accepted.append(listener.accept()[0])
            except TimeoutError:
                continue

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        thread.join()
        for connection in accepted:
            connection.close()
        listener.close()


def free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def ipv6_loopback_available() -> bool:
    try:
        with closing(socket.socket(socket.AF_INET6)) as sock:
            sock.bind(("::1", 0))
    except OSError:
        return False
    return True


needs_ipv6 = pytest.mark.skipif(not ipv6_loopback_available(), reason="no IPv6 loopback")


def test_healthcheck_exits_0_when_the_server_answers_200(tmp_path: Path) -> None:
    with health_server() as port:
        write_config(tmp_path, port=port)

        assert main(["healthcheck"]) == 0


def test_healthcheck_exits_1_when_the_server_answers_500(tmp_path: Path) -> None:
    with health_server(status=500) as port:
        write_config(tmp_path, port=port)

        assert main(["healthcheck"]) == 1


def test_healthcheck_exits_1_when_the_port_is_closed(tmp_path: Path) -> None:
    write_config(tmp_path, port=free_port())

    assert main(["healthcheck"]) == 1


def test_healthcheck_uses_the_port_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(tmp_path, port=free_port())
    with health_server() as port:
        monkeypatch.setenv("TOMARR__SERVER__PORT", str(port))

        assert main(["healthcheck"]) == 0


def test_healthcheck_uses_the_bindaddress_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with health_server() as port:
        write_config(tmp_path, bindaddress="192.0.2.1", port=port)
        monkeypatch.setenv("TOMARR__SERVER__BINDADDRESS", "127.0.0.1")

        assert main(["healthcheck"]) == 0


def test_healthcheck_probes_the_loopback_when_bound_to_every_ipv4_address(
    tmp_path: Path,
) -> None:
    with health_server() as port:
        write_config(tmp_path, bindaddress="0.0.0.0", port=port)

        assert main(["healthcheck"]) == 0


@needs_ipv6
def test_healthcheck_probes_the_ipv4_loopback_when_bound_to_every_address(tmp_path: Path) -> None:
    with health_server() as port:
        write_config(tmp_path, bindaddress="::", port=port)

        assert main(["healthcheck"]) == 0


@needs_ipv6
def test_healthcheck_probes_the_ipv6_loopback_when_bound_to_every_address(tmp_path: Path) -> None:
    with health_server(host="::1") as port:
        write_config(tmp_path, bindaddress="::", port=port)

        assert main(["healthcheck"]) == 0


@needs_ipv6
def test_healthcheck_probes_a_specific_ipv6_address(tmp_path: Path) -> None:
    with health_server(host="::1") as port:
        write_config(tmp_path, bindaddress="::1", port=port)

        assert main(["healthcheck"]) == 0


def test_healthcheck_does_not_follow_a_redirect(tmp_path: Path) -> None:
    with (
        health_server() as target,
        health_server(status=302, location=f"http://127.0.0.1:{target}{HEALTH_PATH}") as port,
    ):
        write_config(tmp_path, port=port)

        assert main(["healthcheck"]) == 1


def test_healthcheck_ignores_the_proxy_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{free_port()}")
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{free_port()}")
    with health_server() as port:
        write_config(tmp_path, port=port)

        assert main(["healthcheck"]) == 0


def test_healthcheck_gives_up_on_a_server_that_never_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(entry, "HEALTHCHECK_TIMEOUT_SECONDS", 0.5)
    with silent_server() as port:
        write_config(tmp_path, port=port)
        started = time.monotonic()

        assert main(["healthcheck"]) == 1

    assert time.monotonic() - started < 3


def test_healthcheck_timeout_is_a_few_seconds() -> None:
    assert 1 <= entry.HEALTHCHECK_TIMEOUT_SECONDS <= 5


def test_healthcheck_exits_1_without_creating_the_config_file(tmp_path: Path) -> None:
    assert main(["healthcheck"]) == 1

    assert list(tmp_path.iterdir()) == []


def test_healthcheck_does_not_create_a_missing_config_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "not-there"
    monkeypatch.setenv("TOMARR_CONFIG_DIR", str(missing))

    assert main(["healthcheck"]) == 1

    assert not missing.exists()


def test_healthcheck_exits_1_on_an_invalid_config_file(tmp_path: Path) -> None:
    write_config(tmp_path, port=70000)

    assert main(["healthcheck"]) == 1


def test_healthcheck_failure_message_does_not_contain_the_api_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_config(tmp_path, port=70000)

    main(["healthcheck"])

    assert caplog.records
    assert API_KEY not in caplog.text
