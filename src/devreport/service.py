"""Оркестрация сбора и формирования отчёта."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from devreport import SCHEMA_VERSION, __version__
from devreport.checks.interpret import build_checks
from devreport.collectors.env import compare_env_files
from devreport.collectors.logs import read_log_tail
from devreport.collectors.ports import check_port
from devreport.collectors.project import collect_project_files
from devreport.collectors.system import collect_system_info
from devreport.collectors.tools import collect_tools
from devreport.config import AppConfig
from devreport.models import LogStats, Report
from devreport.redaction.engine import RedactionEngine, is_dotenv_log_path, mask_dotenv_text
from devreport.renderers.json import render_json
from devreport.renderers.markdown import render_markdown
from devreport.utils.paths import resolve_project_path


@dataclass(frozen=True)
class CollectOptions:
    project: str = "."
    port: int | None = None
    log: str | None = None
    tail: int = 50
    format: str = "markdown"
    tools_enabled: bool = True
    env_enabled: bool = True


DEFAULT_LIMITATIONS: tuple[str, ...] = (
    "Hostname, имя пользователя и домашний каталог не включаются в системный блок по умолчанию",
    "Docker daemon не проверяется (нет docker ps / docker info)",
    "IPv6-порты не проверяются",
    "Состояние TCP-порта может измениться сразу после проверки",
    "Логи читаются только при явном --log; symlink отклоняются",
    "Значения .env никогда не включаются в отчёт",
    "При --log на файл вида .env* значения всех ключей маскируются на границе рендера",
    "Multiline и сложный синтаксис dotenv поддерживаются ограниченно",
    "Автоматическое маскирование неполное и не удаляет все секреты",
    "Команды из директории проверяемого проекта не выполняются",
    "Поддерживаются Windows и Linux; другие ОС не заявляются",
)


def build_report(options: CollectOptions) -> Report:
    project_root = resolve_project_path(options.project)
    system = collect_system_info()

    tools = []
    if options.tools_enabled:
        tools = collect_tools(project_root)

    project_files = collect_project_files(project_root)

    env_comparison = None
    if options.env_enabled:
        env_comparison = compare_env_files(project_root)

    port_result = None
    if options.port is not None:
        port_result = check_port(options.port)

    log_stats: LogStats | None = None
    log_excerpt: str | None = None
    if options.log is not None:
        log_path = Path(options.log).expanduser()
        if not log_path.is_absolute():
            log_path = Path.cwd() / log_path
        read = read_log_tail(log_path, options.tail)
        log_stats = read.stats
        # Сырой хвост: маскирование только через единый RedactionEngine при render
        if read.lines:
            log_excerpt = "\n".join(read.lines)

    checks = build_checks(
        project_root=project_root,
        tools=tools,
        project_files=project_files,
        env_comparison=env_comparison,
        port_check=port_result,
        log_stats=log_stats,
        tools_enabled=options.tools_enabled,
        env_enabled=options.env_enabled,
    )

    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        created_at_utc=created,
        system=system,
        tools=tools,
        project_files=project_files,
        checks=checks,
        env_comparison=env_comparison,
        port_check=port_result,
        log_stats=log_stats if log_stats is not None else LogStats(requested=False),
        log_excerpt=log_excerpt,
        limitations=list(DEFAULT_LIMITATIONS),
    )


def render_report(report: Report, fmt: str) -> str:
    """Единая граница маскирования перед сериализацией.

    Лог-файл с именем .env* дополнительно проходит dotenv-маскирование:
    значения всех ключей скрываются независимо от имени ключа — эвристика
    по имени не покрывает произвольные переменные окружения.
    """
    engine = RedactionEngine()
    if (
        report.log_excerpt
        and report.log_stats is not None
        and is_dotenv_log_path(report.log_stats.path)
    ):
        report = dataclasses.replace(report, log_excerpt=mask_dotenv_text(report.log_excerpt))
    if fmt == "json":
        return render_json(report, engine)
    return render_markdown(report, engine)


def merge_options(
    *,
    config: AppConfig,
    project: str,
    port: int | None,
    log: str | None,
    tail: int | None,
    format_value: str | None,
) -> CollectOptions:
    """CLI явно заданные значения имеют приоритет над конфигом."""
    return CollectOptions(
        project=project,
        port=port,
        log=log,
        tail=tail if tail is not None else config.tail,
        format=format_value if format_value is not None else config.format,
        tools_enabled=config.checks_tools,
        env_enabled=config.checks_env,
    )
