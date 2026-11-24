"""Загрузка и проверка конфигурации .devreport.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devreport.utils.paths import is_symlink, open_regular_file

MAX_CONFIG_BYTES = 64 * 1024
ALLOWED_FORMATS = frozenset({"markdown", "json"})


class ConfigError(Exception):
    """Некорректная конфигурация."""


@dataclass(frozen=True)
class AppConfig:
    format: str = "markdown"
    tail: int = 50
    checks_tools: bool = True
    checks_env: bool = True


DEFAULT_CONFIG = AppConfig()


def load_config(project_root: Path) -> AppConfig:
    path = project_root / ".devreport.toml"
    try:
        if not path.exists():
            return DEFAULT_CONFIG
    except OSError as exc:
        raise ConfigError(f"Не удалось проверить конфигурацию: {exc}") from exc

    if is_symlink(path):
        raise ConfigError("Конфигурационный файл не должен быть symlink")

    try:
        if not path.is_file():
            raise ConfigError(".devreport.toml не является обычным файлом")
        # Атомарное открытие: O_NOFOLLOW закрывает гонку «проверил → открыл»
        fd = open_regular_file(path)
        with os.fdopen(fd, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            if size > MAX_CONFIG_BYTES:
                raise ConfigError(f".devreport.toml превышает лимит {MAX_CONFIG_BYTES} байт")
            raw = handle.read(MAX_CONFIG_BYTES + 1)
    except ConfigError:
        raise
    except OSError as exc:
        raise ConfigError(f"Не удалось прочитать .devreport.toml: {exc}") from exc

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Некорректный TOML: {exc}") from exc

    return _parse_config(data)


def _parse_config(data: dict[str, Any]) -> AppConfig:
    allowed_sections = {"report", "logs", "checks"}
    unknown_sections = set(data.keys()) - allowed_sections
    if unknown_sections:
        names = ", ".join(sorted(unknown_sections))
        raise ConfigError(f"Неизвестные секции конфигурации: {names}")

    fmt = DEFAULT_CONFIG.format
    tail = DEFAULT_CONFIG.tail
    tools = DEFAULT_CONFIG.checks_tools
    env = DEFAULT_CONFIG.checks_env

    report = data.get("report", {})
    if report is not None:
        if not isinstance(report, dict):
            raise ConfigError("[report] должен быть таблицей")
        _reject_unknown_keys("report", report, {"format"})
        if "format" in report:
            fmt = report["format"]
            if not isinstance(fmt, str) or fmt not in ALLOWED_FORMATS:
                raise ConfigError('report.format должен быть "markdown" или "json"')

    logs = data.get("logs", {})
    if logs is not None:
        if not isinstance(logs, dict):
            raise ConfigError("[logs] должен быть таблицей")
        _reject_unknown_keys("logs", logs, {"tail"})
        if "tail" in logs:
            tail = logs["tail"]
            if not isinstance(tail, int) or isinstance(tail, bool):
                raise ConfigError("logs.tail должен быть целым числом")
            if tail < 1 or tail > 1000:
                raise ConfigError("logs.tail должен быть в диапазоне 1–1000")

    checks = data.get("checks", {})
    if checks is not None:
        if not isinstance(checks, dict):
            raise ConfigError("[checks] должен быть таблицей")
        _reject_unknown_keys("checks", checks, {"tools", "env"})
        if "tools" in checks:
            tools = checks["tools"]
            if not isinstance(tools, bool):
                raise ConfigError("checks.tools должен быть boolean")
        if "env" in checks:
            env = checks["env"]
            if not isinstance(env, bool):
                raise ConfigError("checks.env должен быть boolean")

    # Запрещённые возможности — если кто-то положит их в известные секции
    forbidden = {
        "command",
        "commands",
        "log",
        "output",
        "redaction",
        "network",
        "telemetry",
    }
    for section_name, section in data.items():
        if isinstance(section, dict):
            bad = set(section.keys()) & forbidden
            if bad:
                raise ConfigError(
                    f"Запрещённые параметры в [{section_name}]: {', '.join(sorted(bad))}"
                )

    return AppConfig(format=fmt, tail=tail, checks_tools=tools, checks_env=env)


def _reject_unknown_keys(section: str, data: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(data.keys()) - allowed
    if unknown:
        raise ConfigError(f"Неизвестные параметры в [{section}]: {', '.join(sorted(unknown))}")
