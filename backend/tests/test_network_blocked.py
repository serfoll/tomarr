import socket

import pytest


def test_socket_connect_to_remote_host_is_blocked() -> None:
    # 192.0.2.1 is TEST-NET-1 (RFC 5737), so a missing block times out instead of reaching a server.
    with socket.socket() as sock, pytest.raises(RuntimeError, match="Network is disabled"):
        sock.settimeout(1)
        sock.connect(("192.0.2.1", 80))
