"""Markdown-рендерер отчёта."""

from __future__ import annotations

from html import escape

from devreport.models import CheckStatus, Report, ToolStatus
from devreport.redaction.engine import RedactionEngine, sanitize_text


def render_markdown(report: Report, engine: RedactionEngine | None = None) -> str:
    if engine is None:
        engine = RedactionEngine()

    def s(text: str) -> str:
        return sanitize_text(text, engine)

    def se(text: str) -> str:
        # Текст вне code-span: дополнительно экранируем HTML-метасимволы.
        # Значения из внешних источников (stdout команд, содержимое логов)
        # не должны превращаться в inline-HTML/разметку в отчёте.
        return escape(sanitize_text(text, engine), quote=False)

    lines: list[str] = []
    lines.append("# DevReport")
    lines.append("")
    lines.append(f"- schema_version: `{report.schema_version}`")
    lines.append(f"- tool_version: `{s(report.tool_version)}`")
    lines.append(f"- created_at_utc: `{s(report.created_at_utc)}`")
    lines.append("")
    lines.append("> " + s(report.privacy_warning))
    lines.append("")

    lines.append("## Система")
    lines.append("")
    lines.append(f"- ОС: {se(report.system.os_family)} / {se(report.system.os_release)}")
    lines.append(f"- Архитектура: {se(report.system.architecture)}")
    lines.append(f"- Python: {se(report.system.python_version)}")
    lines.append("")

    lines.append("## Инструменты")
    lines.append("")
    if report.tools:
        lines.append("| Имя | Статус | Версия | Детали |")
        lines.append("| --- | --- | --- | --- |")
        for tool in sorted(report.tools, key=lambda t: t.name):
            version = se(tool.version) if tool.version else "—"
            detail = se(tool.detail) if tool.detail else "—"
            status = tool.status.value if isinstance(tool.status, ToolStatus) else str(tool.status)
            lines.append(f"| {s(tool.name)} | `{status}` | {_cell(version)} | {_cell(detail)} |")
    else:
        lines.append("_Инструменты не проверялись._")
    lines.append("")

    lines.append("## Файлы проекта")
    lines.append("")
    for pf in sorted(report.project_files, key=lambda f: f.name):
        mark = "да" if pf.present else "нет"
        lines.append(f"- `{s(pf.name)}`: {mark}")
    lines.append("")

    lines.append("## Проверки")
    lines.append("")
    for check in sorted(report.checks, key=lambda c: c.code):
        status = check.status.value if isinstance(check.status, CheckStatus) else str(check.status)
        lines.append(f"### `{s(check.code)}` — {se(check.title)} [`{status}`]")
        lines.append("")
        lines.append(se(check.description))
        if check.recommendation:
            lines.append("")
            lines.append(f"**Рекомендация:** {se(check.recommendation)}")
        lines.append("")

    if report.env_comparison is not None:
        env = report.env_comparison
        lines.append("## Сравнение .env")
        lines.append("")
        lines.append(f"- status: `{env.status.value}`")
        if env.detail:
            lines.append(f"- detail: {se(env.detail)}")
        lines.append(f"- missing_keys: {_keys(env.missing_keys, s)}")
        lines.append(f"- extra_keys: {_keys(env.extra_keys, s)}")
        lines.append(f"- duplicate_keys: {_keys(env.duplicate_keys, s)}")
        if env.unparsed_lines:
            lines.append("- unparsed_lines: " + ", ".join(str(n) for n in env.unparsed_lines))
        lines.append("")
        lines.append(
            "_Значения переменных никогда не включаются в отчёт. "
            "Multiline и сложный синтаксис dotenv поддерживаются ограниченно._"
        )
        lines.append("")

    if report.port_check is not None:
        port = report.port_check
        lines.append("## Порт")
        lines.append("")
        lines.append(f"- port: `{port.port}`")
        lines.append(f"- status: `{port.status.value}`")
        if port.detail:
            lines.append(f"- detail: {se(port.detail)}")
        lines.append("")

    if report.log_stats is not None and report.log_stats.requested:
        st = report.log_stats
        lines.append("## Лог")
        lines.append("")
        if st.path:
            lines.append(f"- path: `{s(st.path)}`")
        lines.append(f"- lines_returned: {st.lines_returned}")
        lines.append(f"- bytes_read: {st.bytes_read}")
        lines.append(f"- truncated_by_size: {st.truncated_by_size}")
        lines.append(f"- truncated_by_line_length: {st.truncated_by_line_length}")
        lines.append(f"- decoding_replacements: {st.decoding_replacements}")
        if st.rejected_reason:
            lines.append(f"- rejected: {se(st.rejected_reason)}")
        lines.append("")
        if report.log_excerpt:
            fence = _safe_fence(report.log_excerpt)
            lines.append(fence)
            lines.append(s(report.log_excerpt))
            lines.append(fence)
            lines.append("")

    lines.append("## Ограничения диагностики")
    lines.append("")
    for item in sorted(report.limitations):
        lines.append(f"- {se(item)}")
    lines.append("")

    # Без активного HTML: экранируем на всякий случай уже сделано через sanitize;
    # дополнительно не вставляем сырой HTML.
    return "\n".join(lines)


def _keys(keys: tuple[str, ...], s: object) -> str:
    if not keys:
        return "—"
    sanitize = s  # callable
    return ", ".join(f"`{sanitize(k)}`" for k in keys)  # type: ignore[operator]


def _cell(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", " ")
    )


def _safe_fence(content: str) -> str:
    """Подобрать длину code fence, безопасную относительно содержимого."""
    max_ticks = 2
    for line in content.splitlines():
        stripped = line.lstrip()
        count = 0
        for ch in stripped:
            if ch == "`":
                count += 1
            else:
                break
        if count > max_ticks:
            max_ticks = count
    return "`" * (max_ticks + 1)


def escape_html_in_untrusted(text: str) -> str:
    """Дополнительная защита от HTML (используется при необходимости)."""
    return escape(text, quote=True)
