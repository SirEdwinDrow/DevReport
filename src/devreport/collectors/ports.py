"""Проверка доступности локального TCP-порта через bind."""

from __future__ import annotations

import contextlib
import errno
import socket

from devreport.models import CheckStatus, PortCheckResult


def check_port(port: int) -> PortCheckResult:
    """Попытка bind на 127.0.0.1:port.

    IPv6 не проверяется. Состояние порта может измениться.
    """
    if not (1 <= port <= 65535):
        return PortCheckResult(
            status=CheckStatus.UNKNOWN,
            port=port,
            detail="порт вне диапазона 1–65535",
        )

    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Без SO_REUSEADDR: иначе на Windows занятый порт может ошибочно казаться свободным
        sock.bind(("127.0.0.1", port))
        return PortCheckResult(
            status=CheckStatus.OK,
            port=port,
            detail=(
                f"порт {port} на 127.0.0.1 был доступен для bind "
                "(IPv6 не проверялся; состояние может измениться)"
            ),
        )
    except OSError as exc:
        if exc.errno in {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", 10048)}:
            return PortCheckResult(
                status=CheckStatus.WARNING,
                port=port,
                detail=f"порт {port} на 127.0.0.1 занят",
            )
        if exc.errno in {
            errno.EACCES,
            getattr(errno, "EPERM", 1),
            getattr(errno, "WSAEACCES", 10013),
        }:
            return PortCheckResult(
                status=CheckStatus.UNKNOWN,
                port=port,
                detail=f"отказ в доступе при проверке порта {port}",
            )
        return PortCheckResult(
            status=CheckStatus.UNKNOWN,
            port=port,
            detail=f"ошибка проверки порта: {exc.__class__.__name__}",
        )
    finally:
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.close()
