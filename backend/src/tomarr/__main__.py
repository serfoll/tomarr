import logging
import sys
from collections.abc import Sequence
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

import uvicorn

from tomarr.core.config import Server, config_dir, load_settings, read_settings

logger = logging.getLogger(__name__)

GRACEFUL_SHUTDOWN_SECONDS = 5
HEALTHCHECK_TIMEOUT_SECONDS = 3.0
HEALTH_PATH = "/api/v1/system/health"
# A server bound to every address answers on loopback, over either IP version.
WILDCARD_PROBES = {"0.0.0.0": ["127.0.0.1", "::1"], "::": ["127.0.0.1", "::1"]}


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def serve() -> int:
    server = load_settings(config_dir()).server
    # forwarded_allow_ips stays unset, so uvicorn reads FORWARDED_ALLOW_IPS and defaults to
    # loopback only.
    uvicorn.run(
        "tomarr.app:create_app",
        factory=True,
        host=server.bindaddress,
        port=server.port,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        proxy_headers=True,
    )
    return 0


def healthcheck() -> int:
    try:
        server = read_settings(config_dir()).server
    except (OSError, ValueError) as error:
        logger.error("Healthcheck could not read the settings: %s", error)
        return 1
    for host in _probe_hosts(server):
        if _is_healthy(host, server.port):
            return 0
    return 1


def _probe_hosts(server: Server) -> list[str]:
    return WILDCARD_PROBES.get(server.bindaddress, [server.bindaddress])


def _is_healthy(host: str, port: int) -> bool:
    netloc = f"[{host}]" if ":" in host else host
    url = f"http://{netloc}:{port}{HEALTH_PATH}"
    # ProxyHandler({}) keeps a proxy variable in the container from catching a loopback request.
    opener = build_opener(ProxyHandler({}), _NoRedirects)
    try:
        # The status line is enough, so no body is read.
        with opener.open(url, timeout=HEALTHCHECK_TIMEOUT_SECONDS) as response:
            return response.status == 200
    # ValueError is what urllib raises for a host it cannot parse or encode.
    except (OSError, HTTPException, ValueError) as error:
        reason = error.code if isinstance(error, HTTPError) else error
        logger.error("Healthcheck failed on %s: %s", url, reason)
        return False


def main(argv: Sequence[str] = ()) -> int:
    match list(argv):
        case []:
            return serve()
        case ["healthcheck"]:
            return healthcheck()
        case _:
            raise SystemExit(f"Unknown command {' '.join(argv)!r}. Use no argument or healthcheck.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
