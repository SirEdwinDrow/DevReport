"""Проверка внешних инструментов: git, docker, compose."""

from __future__ import annotations

from pathlib import Path

from devreport.models import ToolInfo, ToolStatus
from devreport.utils.subprocess import DEFAULT_TIMEOUT, run_allowed


def collect_tools(
    project_root: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[ToolInfo]:
    tools: list[ToolInfo] = []
    tools.append(_check_version(["git", "--version"], "git", project_root, timeout))
    tools.append(_check_version(["docker", "--version"], "docker", project_root, timeout))
    tools.append(_check_compose(project_root, timeout))
    return tools


def _check_version(
    argv: list[str],
    name: str,
    project_root: Path,
    timeout: float,
) -> ToolInfo:
    result = run_allowed(argv, timeout=timeout, project_root=project_root)
    if result.not_found:
        return ToolInfo(
            name=name,
            status=ToolStatus.NOT_FOUND,
            detail=result.error_detail or "исполняемый файл не найден",
        )
    if result.permission_denied:
        return ToolInfo(
            name=name,
            status=ToolStatus.UNKNOWN,
            detail="отказано в доступе",
        )
    if result.timed_out:
        return ToolInfo(
            name=name,
            status=ToolStatus.TIMEOUT,
            detail="команда превысила timeout",
        )
    if result.returncode is not None and result.returncode != 0:
        return ToolInfo(
            name=name,
            status=ToolStatus.ERROR,
            detail=f"код выхода {result.returncode}",
        )
    version = result.stdout.splitlines()[0].strip() if result.stdout else None
    return ToolInfo(name=name, status=ToolStatus.FOUND, version=version)


def _check_compose(project_root: Path, timeout: float) -> ToolInfo:
    # Сначала docker compose version (plugin)
    plugin = run_allowed(
        ["docker", "compose", "version"],
        timeout=timeout,
        project_root=project_root,
    )
    if plugin.not_found:
        # docker сам отсутствует — compose тоже
        return ToolInfo(
            name="docker-compose",
            status=ToolStatus.NOT_FOUND,
            detail=plugin.error_detail or "docker не найден",
        )
    if not plugin.timed_out and not plugin.permission_denied:
        if plugin.returncode == 0 and plugin.stdout:
            version = plugin.stdout.splitlines()[0].strip()
            return ToolInfo(name="docker-compose", status=ToolStatus.FOUND, version=version)
        # Plugin не сработал — fallback на docker-compose
        if plugin.returncode not in (None, 0):
            pass  # fallback below
        elif plugin.returncode == 0:
            return ToolInfo(
                name="docker-compose",
                status=ToolStatus.FOUND,
                version=plugin.stdout.splitlines()[0].strip() if plugin.stdout else None,
            )

    if plugin.timed_out:
        # Попробуем fallback всё равно? Лучше зафиксировать timeout plugin path
        # но TZ допускает fallback если plugin не найден — timeout это другая ситуация
        pass

    fallback = run_allowed(
        ["docker-compose", "--version"],
        timeout=timeout,
        project_root=project_root,
    )
    if fallback.not_found:
        # Если plugin вернул ошибку, а standalone нет — UNKNOWN/ERROR по plugin
        if plugin.permission_denied:
            return ToolInfo(
                name="docker-compose",
                status=ToolStatus.UNKNOWN,
                detail="отказано в доступе",
            )
        if plugin.timed_out:
            return ToolInfo(
                name="docker-compose",
                status=ToolStatus.TIMEOUT,
                detail="команда превысила timeout",
            )
        if plugin.returncode not in (None, 0):
            return ToolInfo(
                name="docker-compose",
                status=ToolStatus.ERROR,
                detail=f"docker compose: код выхода {plugin.returncode}",
            )
        return ToolInfo(
            name="docker-compose",
            status=ToolStatus.NOT_FOUND,
            detail="Compose plugin и docker-compose не найдены",
        )
    if fallback.permission_denied:
        return ToolInfo(
            name="docker-compose",
            status=ToolStatus.UNKNOWN,
            detail="отказано в доступе",
        )
    if fallback.timed_out:
        return ToolInfo(
            name="docker-compose",
            status=ToolStatus.TIMEOUT,
            detail="команда превысила timeout",
        )
    if fallback.returncode is not None and fallback.returncode != 0:
        return ToolInfo(
            name="docker-compose",
            status=ToolStatus.ERROR,
            detail=f"код выхода {fallback.returncode}",
        )
    fallback_version: str | None = (
        fallback.stdout.splitlines()[0].strip() if fallback.stdout else None
    )
    return ToolInfo(
        name="docker-compose",
        status=ToolStatus.FOUND,
        version=fallback_version,
    )
