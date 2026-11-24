"""Безопасное чтение хвоста лог-файла."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from devreport.models import LogStats
from devreport.utils.paths import is_symlink, open_regular_file

MAX_LOG_BYTES = 1 * 1024 * 1024  # 1 MiB
MAX_LINE_LENGTH = 4 * 1024
MIN_TAIL = 1
MAX_TAIL = 1000


@dataclass
class LogReadResult:
    stats: LogStats
    lines: list[str]


def read_log_tail(path: Path, tail: int) -> LogReadResult:
    """Прочитать хвост лога без загрузки всего файла в память."""
    if tail < MIN_TAIL or tail > MAX_TAIL:
        return LogReadResult(
            stats=LogStats(
                requested=True,
                path=str(path),
                rejected_reason=f"tail должен быть от {MIN_TAIL} до {MAX_TAIL}",
            ),
            lines=[],
        )

    try:
        if is_symlink(path):
            return LogReadResult(
                stats=LogStats(
                    requested=True,
                    path=str(path),
                    rejected_reason="symlink для логов в MVP отклоняется",
                ),
                lines=[],
            )
        if not path.exists():
            return LogReadResult(
                stats=LogStats(
                    requested=True,
                    path=str(path),
                    rejected_reason="файл не найден",
                ),
                lines=[],
            )
        if path.is_dir():
            return LogReadResult(
                stats=LogStats(
                    requested=True,
                    path=str(path),
                    rejected_reason="указана директория, ожидался файл",
                ),
                lines=[],
            )
        if not path.is_file():
            return LogReadResult(
                stats=LogStats(
                    requested=True,
                    path=str(path),
                    rejected_reason="не обычный файл (FIFO/device отклоняются)",
                ),
                lines=[],
            )
    except OSError as exc:
        return LogReadResult(
            stats=LogStats(
                requested=True,
                path=str(path),
                rejected_reason=f"ошибка доступа: {exc.__class__.__name__}",
            ),
            lines=[],
        )

    # Атомарное открытие: O_NOFOLLOW на POSIX закрывает гонку
    # «is_symlink → stat → open», fstat отсекает не-файлы.
    try:
        fd = open_regular_file(path)
    except OSError as exc:
        return LogReadResult(
            stats=LogStats(
                requested=True,
                path=str(path),
                rejected_reason=f"чтение: {exc.__class__.__name__}",
            ),
            lines=[],
        )

    try:
        with os.fdopen(fd, "rb") as handle:
            file_size = os.fstat(handle.fileno()).st_size
            read_size = min(file_size, MAX_LOG_BYTES)
            truncated_by_size = file_size > MAX_LOG_BYTES
            offset = max(0, file_size - read_size)
            handle.seek(offset)
            raw = handle.read(read_size)
    except OSError as exc:
        return LogReadResult(
            stats=LogStats(
                requested=True,
                path=str(path),
                rejected_reason=f"чтение: {exc.__class__.__name__}",
            ),
            lines=[],
        )

    # Если читали не с начала — возможно обрезали середину строки
    if offset > 0:
        nl = raw.find(b"\n")
        if nl != -1:
            raw = raw[nl + 1 :]
        truncated_by_size = True

    text = raw.decode("utf-8", errors="replace")
    decoding_replacements = "\ufffd" in text

    all_lines = text.splitlines()
    selected = all_lines[-tail:] if tail < len(all_lines) else all_lines

    truncated_by_line_length = False
    limited: list[str] = []
    for line in selected:
        if len(line) > MAX_LINE_LENGTH:
            limited.append(line[:MAX_LINE_LENGTH] + "…")
            truncated_by_line_length = True
        else:
            limited.append(line)

    stats = LogStats(
        requested=True,
        path=str(path),
        lines_returned=len(limited),
        bytes_read=len(raw),
        truncated_by_size=truncated_by_size,
        truncated_by_line_length=truncated_by_line_length,
        decoding_replacements=decoding_replacements,
    )
    return LogReadResult(stats=stats, lines=limited)
