"""Безопасный запуск внешних команд с allowlist."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT = 5.0
MAX_OUTPUT_BYTES = 8 * 1024

# Только эти имена исполняемых файлов разрешены
_ALLOWED_BASE: frozenset[str] = frozenset({"git", "docker", "docker-compose"})
ALLOWED_COMMANDS: frozenset[str] = _ALLOWED_BASE | frozenset(
    f"{name}.exe" for name in _ALLOWED_BASE
)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    timed_out: bool = False
    not_found: bool = False
    permission_denied: bool = False
    error_detail: str | None = None


def is_allowed_command(executable: str) -> bool:
    """Разрешены только точные имена git/docker/docker-compose.

    Суффикс .exe допускается только на Windows: на Linux исполняемый файл
    может называться git.sh/git.com/git.foo и быть скриптом — расширение
    там не является маркером исполняемости.
    """
    name = Path(executable).name.lower()
    if name in _ALLOWED_BASE:
        return True
    if sys.platform == "win32" and name.endswith(".exe"):
        return name[: -len(".exe")] in _ALLOWED_BASE
    return False


def _path_entries() -> list[Path]:
    raw = os.environ.get("PATH", "")
    parts = raw.split(os.pathsep)
    result: list[Path] = []
    for part in parts:
        if not part or part == "." or part == "":
            continue
        # Относительные записи PATH пропускаем — они опасны
        p = Path(part)
        if not p.is_absolute():
            continue
        result.append(p)
    return result


def find_executable(name: str, *, project_root: Path | None = None) -> Path | None:
    """Найти исполняемый файл, исключая cwd и пути внутри project_root."""
    if not is_allowed_command(name):
        return None

    # Не используем shutil.which напрямую: он учитывает cwd
    names = [name]
    if sys.platform == "win32":
        lower = name.lower()
        if not lower.endswith((".exe", ".bat", ".cmd", ".com")):
            names = [f"{name}.exe"]
        # .bat/.cmd намеренно не запускаем через shell — пропускаем

    search_dirs = _path_entries()
    # На Windows также PATHEXT, но мы ищем только .exe для безопасности
    try:
        cwd = Path.cwd()
    except OSError:
        cwd = None
    for directory in search_dirs:
        try:
            from devreport.utils.paths import path_is_under

            # Не исполняем бинарники из проверяемого проекта и из cwd:
            # cwd может не совпадать с project_root (--project указывает иначе).
            if project_root is not None and path_is_under(directory, project_root):
                continue
            if cwd is not None and path_is_under(directory, cwd):
                continue
        except OSError:
            continue
        for candidate_name in names:
            candidate = directory / candidate_name
            try:
                if candidate.is_symlink():
                    # Разрешаем symlink вне project_root, если указывает на файл
                    pass
                if not candidate.is_file():
                    continue
                if sys.platform != "win32" and not os.access(candidate, os.X_OK):
                    continue
                # Исполняем только бессуффиксные файлы и .exe:
                # .bat/.cmd/.com/.ps1 могут обойти ограничения интерпретатора
                if candidate.suffix.lower() not in {"", ".exe"}:
                    continue
                return candidate
            except OSError:
                continue

    # Fallback: shutil.which, но отфильтруем cwd/project
    which = shutil.which(name)
    if which is None and sys.platform == "win32":
        which = shutil.which(f"{name}.exe")
    if which is None:
        return None
    found = Path(which)
    try:
        # Исключаем текущую директорию (и всё под ней)
        from devreport.utils.paths import path_is_under

        if path_is_under(found.parent, Path.cwd()):
            return None
        if project_root is not None and path_is_under(found.parent, project_root):
            return None
        # shutil.which на Windows может вернуть .com/.bat/.ps1 через PATHEXT
        if found.suffix.lower() not in {"", ".exe"}:
            return None
        return found
    except OSError:
        return None


def run_allowed(
    argv: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    project_root: Path | None = None,
) -> CommandResult:
    """Запустить разрешённую команду со shell=False."""
    if not argv:
        return CommandResult(
            argv=(),
            returncode=None,
            stdout="",
            error_detail="empty argv",
            not_found=True,
        )

    cmd_name = argv[0]
    if not is_allowed_command(cmd_name):
        return CommandResult(
            argv=tuple(argv),
            returncode=None,
            stdout="",
            error_detail="command not in allowlist",
            not_found=True,
        )

    # Если передан просто basename — ищем в PATH
    executable: str
    if Path(cmd_name).name == cmd_name:
        found = find_executable(cmd_name, project_root=project_root)
        if found is None:
            return CommandResult(
                argv=tuple(argv),
                returncode=None,
                stdout="",
                not_found=True,
                error_detail="executable not found in PATH",
            )
        executable = str(found)
    else:
        # Абсолютный/относительный путь — только если имя в allowlist и вне project
        path = Path(cmd_name)
        if project_root is not None:
            from devreport.utils.paths import path_is_under

            try:
                if path_is_under(path.parent if path.parent != path else path, project_root):
                    return CommandResult(
                        argv=tuple(argv),
                        returncode=None,
                        stdout="",
                        not_found=True,
                        error_detail="refusing executable inside project root",
                    )
            except OSError:
                pass
        from devreport.utils.paths import is_regular_file

        if not is_regular_file(path):
            return CommandResult(
                argv=tuple(argv),
                returncode=None,
                stdout="",
                not_found=True,
                error_detail="not a regular file or symlink",
            )
        if path.suffix.lower() in {".bat", ".cmd"}:
            return CommandResult(
                argv=tuple(argv),
                returncode=None,
                stdout="",
                error_detail="refusing to execute .bat/.cmd",
                not_found=True,
            )
        executable = str(path)

    full_argv = [executable, *argv[1:]]
    try:
        completed = subprocess.run(
            full_argv,
            shell=False,
            capture_output=True,
            timeout=timeout,
            check=False,
            text=False,
        )
    except FileNotFoundError:
        return CommandResult(
            argv=tuple(full_argv),
            returncode=None,
            stdout="",
            not_found=True,
            error_detail="FileNotFoundError",
        )
    except PermissionError:
        return CommandResult(
            argv=tuple(full_argv),
            returncode=None,
            stdout="",
            permission_denied=True,
            error_detail="PermissionError",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_limited(exc.stdout)
        return CommandResult(
            argv=tuple(full_argv),
            returncode=None,
            stdout=stdout,
            timed_out=True,
            error_detail="TimeoutExpired",
        )
    except OSError as exc:
        return CommandResult(
            argv=tuple(full_argv),
            returncode=None,
            stdout="",
            error_detail=f"OSError: {exc.__class__.__name__}",
        )

    stdout = _decode_limited(completed.stdout)
    # stderr намеренно не включаем в отчёт
    return CommandResult(
        argv=tuple(full_argv),
        returncode=completed.returncode,
        stdout=stdout,
    )


def _decode_limited(data: bytes | str | None) -> str:
    if data is None:
        return ""
    raw = data.encode("utf-8", errors="replace") if isinstance(data, str) else data
    truncated = raw[:MAX_OUTPUT_BYTES]
    return truncated.decode("utf-8", errors="replace").strip()
