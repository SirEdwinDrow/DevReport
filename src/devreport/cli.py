"""CLI DevReport на Typer."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from devreport import __version__
from devreport.config import ConfigError, load_config
from devreport.models import CheckStatus
from devreport.service import build_report, merge_options, render_report
from devreport.utils.io import OutputError, write_report_file
from devreport.utils.paths import resolve_project_path

# stdout — только полный отчёт; stderr — сводка/прогресс/предупреждения
err_console = Console(stderr=True)
out_console = Console()

app = typer.Typer(
    name="devreport",
    help="DevReport — подготовка диагностических отчётов о локальном окружении проекта.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"devreport {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Показать версию и выйти.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Кроссплатформенная утилита диагностических отчётов."""


@app.command("collect")
def collect_cmd(
    project: Annotated[
        str,
        typer.Option("--project", help="Корневая директория проекта (по умолчанию: текущая)."),
    ] = ".",
    port: Annotated[
        int | None,
        typer.Option(
            "--port",
            help="Проверить доступность TCP-порта на 127.0.0.1 (bind).",
            min=1,
            max=65535,
        ),
    ] = None,
    log: Annotated[
        Path | None,
        typer.Option(
            "--log",
            help="Явно добавить хвост указанного лог-файла.",
            exists=False,
            dir_okay=False,
            readable=False,
        ),
    ] = None,
    tail: Annotated[
        int | None,
        typer.Option(
            "--tail",
            help="Число последних строк лога (1–1000). По умолчанию: 50 или из конфига.",
            min=1,
            max=1000,
        ),
    ] = None,
    format_value: Annotated[
        str | None,
        typer.Option(
            "--format",
            help="Формат отчёта: markdown или json. По умолчанию: markdown или из конфига.",
            case_sensitive=False,
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Записать отчёт в файл. Без этого флага отчёт идёт в stdout.",
        ),
    ] = None,
    preview: Annotated[
        bool,
        typer.Option("--preview", help="Сформировать и показать отчёт без записи файла."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Перезаписать существующий файл --output."),
    ] = False,
) -> None:
    """Собрать диагностический отчёт о проекте и окружении."""
    try:
        _run_collect(
            project=project,
            port=port,
            log=log,
            tail=tail,
            format_value=format_value,
            output=output,
            preview=preview,
            force=force,
        )
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        err_console.print("[yellow]Прервано пользователем.[/yellow]")
        raise typer.Exit(1) from None
    except ConfigError as exc:
        err_console.print(f"[red]Ошибка конфигурации:[/red] {exc}")
        raise typer.Exit(2) from None
    except OutputError as exc:
        err_console.print(f"[red]Ошибка записи:[/red] {exc}")
        raise typer.Exit(1) from None
    except ValueError as exc:
        err_console.print(f"[red]Некорректные аргументы:[/red] {exc}")
        raise typer.Exit(2) from None
    except OSError as exc:
        err_console.print(f"[red]Ошибка:[/red] {exc}")
        raise typer.Exit(1) from None
    except Exception as exc:  # noqa: BLE001 — граница CLI
        err_console.print(f"[red]Внутренняя ошибка:[/red] {exc}")
        raise typer.Exit(1) from None


def _run_collect(
    *,
    project: str,
    port: int | None,
    log: Path | None,
    tail: int | None,
    format_value: str | None,
    output: Path | None,
    preview: bool,
    force: bool,
) -> None:
    if preview and output is not None:
        raise ValueError("Нельзя одновременно использовать --preview и --output")

    if format_value is not None:
        normalized = format_value.lower().strip()
        if normalized not in {"markdown", "json"}:
            raise ValueError('--format должен быть "markdown" или "json"')
        format_value = normalized

    project_root = resolve_project_path(project)
    if not project_root.exists():
        raise ValueError(f"Директория проекта не существует: {project_root}")
    if not project_root.is_dir():
        raise ValueError(f"Путь проекта не является директорией: {project_root}")

    config = load_config(project_root)
    options = merge_options(
        config=config,
        project=str(project_root),
        port=port,
        log=str(log) if log is not None else None,
        tail=tail,
        format_value=format_value,
    )

    err_console.print("[dim]Сбор диагностики…[/dim]")
    report = build_report(options)
    rendered = render_report(report, options.format)

    _print_summary(report)

    if output is not None and not preview:
        write_report_file(Path(output), rendered, force=force)
        err_console.print(f"[green]Отчёт записан:[/green] {output}")
    else:
        # Полный отчёт в stdout без загрязнения (особенно для JSON)
        sys.stdout.write(rendered)
        if not rendered.endswith("\n"):
            sys.stdout.write("\n")


def _print_summary(report: object) -> None:
    from devreport.models import Report

    assert isinstance(report, Report)
    table = Table(title="Сводка DevReport", show_header=True, header_style="bold")
    table.add_column("Код")
    table.add_column("Статус")
    table.add_column("Заголовок")

    status_style = {
        CheckStatus.OK: "green",
        CheckStatus.WARNING: "yellow",
        CheckStatus.ERROR: "red",
        CheckStatus.SKIPPED: "dim",
        CheckStatus.UNKNOWN: "magenta",
    }
    for check in sorted(report.checks, key=lambda c: c.code):
        style = status_style.get(check.status, "")
        table.add_row(check.code, f"[{style}]{check.status.value}[/{style}]", check.title)

    err_console.print(table)
    err_console.print(f"[yellow]{report.privacy_warning}[/yellow]")


def run() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    app()
