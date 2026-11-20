"""Интеграционные тесты CLI через CliRunner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from devreport.cli import app
from devreport.models import ToolInfo, ToolStatus
from devreport.utils.subprocess import CommandResult

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "DevReport" in result.stdout or "devreport" in result.stdout.lower()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "devreport" in result.stdout


def test_collect_preview_empty_project(project_dir: Path) -> None:
    with patch(
        "devreport.collectors.tools.run_allowed",
        return_value=CommandResult(
            argv=("git", "--version"),
            returncode=None,
            stdout="",
            not_found=True,
        ),
    ):
        result = runner.invoke(
            app,
            ["collect", "--project", str(project_dir), "--preview", "--format", "markdown"],
        )
    assert result.exit_code == 0
    assert "DevReport" in result.stdout
    assert "schema_version" in result.stdout


def test_preview_and_output_conflict(project_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "r.md"
    result = runner.invoke(
        app,
        [
            "collect",
            "--project",
            str(project_dir),
            "--preview",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 2


def test_json_stdout_is_clean(project_dir: Path) -> None:
    with patch(
        "devreport.collectors.tools.collect_tools",
        return_value=[
            ToolInfo(name="git", status=ToolStatus.NOT_FOUND, detail="missing"),
        ],
    ):
        result = runner.invoke(
            app,
            ["collect", "--project", str(project_dir), "--format", "json"],
        )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["schema_version"] == "1.0"
    assert "privacy_warning" in data


def test_output_file(project_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    with patch(
        "devreport.collectors.tools.collect_tools",
        return_value=[],
    ):
        result = runner.invoke(
            app,
            [
                "collect",
                "--project",
                str(project_dir),
                "--output",
                str(out),
                "--format",
                "markdown",
            ],
        )
    assert result.exit_code == 0
    assert out.exists()
    assert "DevReport" in out.read_text(encoding="utf-8")


def test_log_not_read_without_flag(project_dir: Path, tmp_path: Path) -> None:
    secret_log = tmp_path / "secret.log"
    secret_log.write_text("password=should-not-appear\n", encoding="utf-8")
    with patch("devreport.collectors.tools.collect_tools", return_value=[]):
        result = runner.invoke(
            app,
            ["collect", "--project", str(project_dir), "--format", "json"],
        )
    assert result.exit_code == 0
    assert "should-not-appear" not in result.stdout
    data = json.loads(result.stdout)
    assert data["log_stats"]["requested"] is False


def test_log_with_redaction(project_dir: Path, tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text(
        "password=supersecret\nuser@example.com\n",
        encoding="utf-8",
    )
    with patch("devreport.collectors.tools.collect_tools", return_value=[]):
        result = runner.invoke(
            app,
            [
                "collect",
                "--project",
                str(project_dir),
                "--log",
                str(log),
                "--format",
                "json",
            ],
        )
    assert result.exit_code == 0
    assert "supersecret" not in result.stdout
    assert "user@example.com" not in result.stdout
    data = json.loads(result.stdout)
    assert data["log_stats"]["requested"] is True


def test_env_values_not_in_report(sample_env_pair: Path) -> None:
    with patch("devreport.collectors.tools.collect_tools", return_value=[]):
        result = runner.invoke(
            app,
            ["collect", "--project", str(sample_env_pair), "--format", "json"],
        )
    assert result.exit_code == 0
    assert "postgres://u:p@localhost/db" not in result.stdout
    data = json.loads(result.stdout)
    assert "SECRET_KEY" in data["env_comparison"]["missing_keys"]


def test_bad_config_exit_2(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text(
        "[report]\nformat = 123\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["collect", "--project", str(project_dir)])
    assert result.exit_code == 2
