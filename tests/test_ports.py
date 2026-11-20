"""Тесты проверки порта."""

from __future__ import annotations

import socket

from devreport.collectors.ports import check_port
from devreport.models import CheckStatus


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_port_available() -> None:
    port = _free_port()
    result = check_port(port)
    assert result.status == CheckStatus.OK
    assert result.port == port


def test_port_in_use() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        port = int(holder.getsockname()[1])
        holder.listen(1)
        result = check_port(port)
        assert result.status == CheckStatus.WARNING


def test_port_out_of_range() -> None:
    result = check_port(0)
    assert result.status == CheckStatus.UNKNOWN
