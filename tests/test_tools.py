"""Тесты проверки инструментов с моками."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from devreport.collectors.tools import collect_tools
from devreport.models import ToolStatus
from devreport.utils.subprocess import CommandResult


def _ok(argv: list[str], stdout: str) -> CommandResult:
    return CommandResult(argv=tuple(argv), returncode=0, stdout=stdout)


def test_tools_found(project_dir: Path) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> CommandResult:
        if argv[:2] == ["git", "--version"]:
            return _ok(argv, "git version 2.45.0")
        if argv[:2] == ["docker", "--version"]:
            return _ok(argv, "Docker version 26.0.0")
        if argv[:3] == ["docker", "compose", "version"]:
            return _ok(argv, "Docker Compose version v2.27.0")
        return CommandResult(argv=tuple(argv), returncode=1, stdout="", not_found=True)

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake_run):
        tools = {t.name: t for t in collect_tools(project_dir)}
    assert tools["git"].status == ToolStatus.FOUND
    assert tools["docker"].status == ToolStatus.FOUND
    assert tools["docker-compose"].status == ToolStatus.FOUND


def test_tools_not_found(project_dir: Path) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> CommandResult:
        return CommandResult(
            argv=tuple(argv),
            returncode=None,
            stdout="",
            not_found=True,
            error_detail="missing",
        )

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake_run):
        tools = collect_tools(project_dir)
    assert all(t.status == ToolStatus.NOT_FOUND for t in tools)


def test_compose_fallback(project_dir: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> CommandResult:
        calls.append(list(argv))
        if argv[:2] == ["git", "--version"]:
            return _ok(argv, "git version 2.0")
        if argv[:2] == ["docker", "--version"]:
            return _ok(argv, "Docker version 1")
        if argv[:3] == ["docker", "compose", "version"]:
            return CommandResult(argv=tuple(argv), returncode=1, stdout="")
        if argv[:2] == ["docker-compose", "--version"]:
            return _ok(argv, "docker-compose version 1.29.2")
        return CommandResult(argv=tuple(argv), returncode=None, stdout="", not_found=True)

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake_run):
        tools = {t.name: t for t in collect_tools(project_dir)}
    assert tools["docker-compose"].status == ToolStatus.FOUND
    assert any(c[:2] == ["docker-compose", "--version"] for c in calls)


def test_timeout_status(project_dir: Path) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> CommandResult:
        return CommandResult(argv=tuple(argv), returncode=None, stdout="", timed_out=True)

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake_run):
        tools = collect_tools(project_dir)
    assert all(t.status == ToolStatus.TIMEOUT for t in tools)
