"""Построение списка проверок из собранных фактов."""

from __future__ import annotations

from pathlib import Path

from devreport.models import (
    CheckResult,
    CheckStatus,
    EnvComparison,
    LogStats,
    PortCheckResult,
    ProjectFileInfo,
    ToolInfo,
    ToolStatus,
)


def build_checks(
    *,
    project_root: Path,
    tools: list[ToolInfo],
    project_files: list[ProjectFileInfo],
    env_comparison: EnvComparison | None,
    port_check: PortCheckResult | None,
    log_stats: LogStats | None,
    tools_enabled: bool = True,
    env_enabled: bool = True,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            code="project.root",
            status=CheckStatus.OK if project_root.exists() else CheckStatus.ERROR,
            title="Корень проекта",
            description=f"Проверяемый каталог: {project_root.name}",
            recommendation=None if project_root.exists() else "Укажите существующий --project",
        )
    )

    if tools_enabled:
        checks.extend(_tool_checks(tools))
    else:
        checks.append(
            CheckResult(
                code="tools.disabled",
                status=CheckStatus.SKIPPED,
                title="Проверка инструментов",
                description="Отключено в конфигурации",
            )
        )

    present = {f.name for f in project_files if f.present}
    checks.append(
        CheckResult(
            code="project.manifest",
            status=CheckStatus.OK if present else CheckStatus.WARNING,
            title="Файлы проекта",
            description=(
                f"Найдено известных файлов: {len(present)}"
                if present
                else "В корне не найдено известных файлов проекта"
            ),
        )
    )

    if env_enabled:
        if env_comparison is not None:
            checks.append(_env_check(env_comparison))
    else:
        checks.append(
            CheckResult(
                code="env.disabled",
                status=CheckStatus.SKIPPED,
                title="Сравнение .env",
                description="Отключено в конфигурации",
            )
        )

    if port_check is not None:
        checks.append(
            CheckResult(
                code="port.bind",
                status=port_check.status,
                title=f"Порт {port_check.port}",
                description=port_check.detail or "",
                recommendation=(
                    "Освободите порт или выберите другой"
                    if port_check.status == CheckStatus.WARNING
                    else None
                ),
            )
        )
    else:
        checks.append(
            CheckResult(
                code="port.bind",
                status=CheckStatus.SKIPPED,
                title="Проверка порта",
                description="Порт не указан (--port не задан)",
            )
        )

    if log_stats is not None and log_stats.requested:
        if log_stats.rejected_reason:
            checks.append(
                CheckResult(
                    code="logs.read",
                    status=CheckStatus.ERROR,
                    title="Чтение лога",
                    description=log_stats.rejected_reason,
                )
            )
        else:
            desc = f"Строк: {log_stats.lines_returned}, байт: {log_stats.bytes_read}"
            if log_stats.truncated_by_size:
                desc += "; усечено по размеру"
            if log_stats.decoding_replacements:
                desc += "; замены при декодировании UTF-8"
            checks.append(
                CheckResult(
                    code="logs.read",
                    status=CheckStatus.OK,
                    title="Чтение лога",
                    description=desc,
                )
            )
    else:
        checks.append(
            CheckResult(
                code="logs.read",
                status=CheckStatus.SKIPPED,
                title="Чтение лога",
                description="Лог не запрошен (--log не задан)",
            )
        )

    checks.append(
        CheckResult(
            code="docker.daemon",
            status=CheckStatus.SKIPPED,
            title="Docker daemon",
            description=(
                "Доступность Docker daemon не проверялась (не запускаются docker ps / docker info)"
            ),
        )
    )

    return checks


def _tool_checks(tools: list[ToolInfo]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for tool in tools:
        code = f"tools.{tool.name}"
        if tool.status == ToolStatus.FOUND:
            results.append(
                CheckResult(
                    code=code,
                    status=CheckStatus.OK,
                    title=f"{tool.name}",
                    description=tool.version or "версия получена",
                )
            )
        elif tool.status == ToolStatus.NOT_FOUND:
            results.append(
                CheckResult(
                    code=code,
                    status=CheckStatus.WARNING,
                    title=f"{tool.name}",
                    description=tool.detail or "не найден",
                    recommendation=f"Установите {tool.name}, если он нужен проекту",
                )
            )
        elif tool.status == ToolStatus.TIMEOUT:
            results.append(
                CheckResult(
                    code=code,
                    status=CheckStatus.UNKNOWN,
                    title=f"{tool.name}",
                    description=tool.detail or "timeout",
                )
            )
        elif tool.status == ToolStatus.ERROR:
            results.append(
                CheckResult(
                    code=code,
                    status=CheckStatus.ERROR,
                    title=f"{tool.name}",
                    description=tool.detail or "ошибка выполнения",
                )
            )
        else:
            results.append(
                CheckResult(
                    code=code,
                    status=CheckStatus.UNKNOWN,
                    title=f"{tool.name}",
                    description=tool.detail or "результат неизвестен",
                )
            )
    return results


def _env_check(env: EnvComparison) -> CheckResult:
    parts: list[str] = []
    if env.detail:
        parts.append(env.detail)
    if env.missing_keys:
        parts.append("отсутствуют ключи: " + ", ".join(env.missing_keys))
    if env.extra_keys:
        parts.append("дополнительные ключи: " + ", ".join(env.extra_keys))
    if env.duplicate_keys:
        parts.append("повторяющиеся ключи: " + ", ".join(env.duplicate_keys))
    if env.unparsed_lines:
        parts.append("нераспознанные строки: " + ", ".join(str(n) for n in env.unparsed_lines))
    if not parts:
        parts.append("наборы ключей согласованы")
    recommendation = None
    if env.status == CheckStatus.WARNING and env.missing_keys:
        recommendation = "Добавьте отсутствующие ключи в .env (значения не включаются в отчёт)"
    return CheckResult(
        code="env.keys",
        status=env.status,
        title="Сравнение .env",
        description="; ".join(parts),
        recommendation=recommendation,
    )
