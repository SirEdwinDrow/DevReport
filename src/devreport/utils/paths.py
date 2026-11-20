"""Безопасная работа с путями."""

from __future__ import annotations

import os
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
