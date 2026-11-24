"""Безопасная работа с путями."""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path


def resolve_project_path(project: str | Path) -> Path:
    """Разрешить путь к проекту без следования symlink для корня отчёта."""
    path = Path(project).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    # resolve(strict=False) нормализует .., но следует symlink —
    # для корня проекта используем absolute + normpath без follow.
    return Path(os.path.normpath(str(path.absolute())))


def is_symlink(path: Path) -> bool:
    try:
        return path.is_symlink()
    except OSError:
        return False


def is_regular_file(path: Path) -> bool:
    """True только для обычного файла (не dir/fifo/device/symlink)."""
    try:
        if path.is_symlink():
            return False
        return path.is_file()
    except OSError:
        return False


def ensure_inside_or_equal(path: Path, root: Path) -> bool:
    """Проверить, что path находится внутри root или равен ему."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def path_is_under(candidate: Path, root: Path) -> bool:
    """True, если candidate лежит под root (включая сам root)."""
    try:
        cand = Path(os.path.normpath(str(candidate.absolute())))
        base = Path(os.path.normpath(str(root.absolute())))
        try:
            cand.relative_to(base)
            return True
        except ValueError:
            return False
    except OSError:
        return False


def open_regular_file(path: Path) -> int:
    """Атомарно открыть файл на чтение, отклоняя symlink и не-файлы.

    На POSIX используется O_NOFOLLOW: symlink отклоняется ядром в момент
    open(), что закрывает гонку «проверил is_symlink → открыл» (TOCTOU).
    На Windows O_NOFOLLOW нет — предварительная проверка is_symlink() и
    повторная проверка после open() остаются best-effort (без прав
    администратора нельзя открыть reparse point без follow), но fstat
    после open() всё равно отсекает директории/FIFO/устройства.

    Возвращает файловый дескриптор (клиент обязан закрыть).
    Бросает OSError при отказе или ошибке доступа.
    """
    if sys.platform == "win32" and is_symlink(path):
        raise OSError(errno.ELOOP, "symlink refused", str(path))

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
        # Windows: повторная проверка — если путь стал reparse point между
        # pre-check и open, отказываемся (best-effort без admin).
        if sys.platform == "win32" and is_symlink(path):
            raise OSError(errno.ELOOP, "symlink refused", str(path))
    except BaseException:
        os.close(fd)
        raise
    return fd
