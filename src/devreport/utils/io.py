"""Безопасная запись отчётов."""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

from devreport.utils.paths import is_symlink


class OutputError(Exception):
    """Ошибка записи выходного файла."""


def write_report_file(path: Path, content: str, *, force: bool = False) -> None:
    """Атомарно записать отчёт в файл.

    Не создаёт отсутствующие родительские директории.
    Не перезаписывает существующий файл без force.
    Отклоняет symlink в качестве конечного файла.
    """
    path = Path(path)
    parent = path.parent

    if not parent.exists():
        raise OutputError(f"Родительская директория не существует: {parent}")
    if not parent.is_dir():
        raise OutputError(f"Родительский путь не является директорией: {parent}")

    if path.exists():
        if is_symlink(path):
            raise OutputError(f"Отказ: путь является symlink: {path}")
        if not force:
            raise OutputError(f"Файл уже существует: {path}. Используйте --force для перезаписи.")
        if path.is_dir():
            raise OutputError(f"Путь является директорией: {path}")

    # Если путь ещё не существует, но является dangling symlink
    if is_symlink(path):
        raise OutputError(f"Отказ: путь является symlink: {path}")

    data = content.encode("utf-8")
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".devreport-",
            suffix=".tmp",
            dir=str(parent),
        )
        tmp_path = Path(tmp_name)
        try:
            if sys.platform != "win32":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise

        # На Windows replace работает для существующих файлов
        os.replace(str(tmp_path), str(path))
        tmp_path = None

        if sys.platform != "win32":
            with contextlib.suppress(OSError):
                os.chmod(path, 0o600)
    except OutputError:
        raise
    except OSError as exc:
        raise OutputError(f"Не удалось записать файл: {exc}") from exc
    finally:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
