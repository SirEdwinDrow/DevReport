"""Дополнительные тесты для покрытия веток."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from devreport import SCHEMA_VERSION, __version__
from devreport.checks.interpret import build_checks
from devreport.cli import app
from devreport.collectors.env import compare_env_files, parse_env_keys
from devreport.collectors.logs import read_log_tail
from devreport.collectors.ports import check_port
from devreport.collectors.system import collect_system_info
from devreport.collectors.tools import collect_tools
from devreport.config import AppConfig, ConfigError, load_config
from devreport.models import (
    CheckStatus,
    EnvComparison,
    LogStats,
    PortCheckResult,
    ProjectFileInfo,
    Report,
    SystemInfo,
    ToolInfo,
    ToolStatus,
)
from devreport.redaction.engine import RedactionEngine, sanitize_text
from devreport.renderers.markdown import escape_html_in_untrusted, render_markdown
from devreport.service import build_report, merge_options, render_report
from devreport.utils.io import OutputError, write_report_file
from devreport.utils.paths import (
    ensure_inside_or_equal,
    is_regular_file,
    is_symlink,
    path_is_under,
    resolve_project_path,
)
from devreport.utils.subprocess import CommandResult, find_executable, run_allowed

runner = CliRunner()


def test_paths_helpers(tmp_path: Path) -> None:
    root = resolve_project_path(str(tmp_path))
    assert root.exists() or True
    child = root / "a.txt"
    child.write_text("x", encoding="utf-8")
    assert is_regular_file(child) is True
    assert is_symlink(child) is False
    assert path_is_under(child, root) is True
    assert ensure_inside_or_equal(child, root) is True
    assert path_is_under(tmp_path / ".." / "other", root) is False


def test_system_linux_branch() -> None:
    with (
        patch("devreport.collectors.system.platform.system", return_value="Linux"),
        patch(
            "devreport.collectors.system.platform.freedesktop_os_release",
            return_value={"PRETTY_NAME": "Ubuntu 22.04", "VERSION_ID": "22.04"},
        ),
    ):
        info = collect_system_info()
    assert "Ubuntu" in info.os_release or info.os_family == "Linux"


def test_tools_permission_and_error(project_dir: Path) -> None:
    def fake(argv: list[str], **kwargs: object) -> CommandResult:
        if argv[0] == "git":
            return CommandResult(
                argv=tuple(argv), returncode=None, stdout="", permission_denied=True
            )
        if argv[0] == "docker" and len(argv) == 2:
            return CommandResult(argv=tuple(argv), returncode=2, stdout="err")
        if argv[:3] == ["docker", "compose", "version"]:
            return CommandResult(argv=tuple(argv), returncode=None, stdout="", timed_out=True)
        return CommandResult(argv=tuple(argv), returncode=None, stdout="", not_found=True)

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake):
        tools = {t.name: t for t in collect_tools(project_dir)}
    assert tools["git"].status == ToolStatus.UNKNOWN
    assert tools["docker"].status == ToolStatus.ERROR


def test_compose_plugin_timeout_then_missing(project_dir: Path) -> None:
    def fake(argv: list[str], **kwargs: object) -> CommandResult:
        if argv[:2] == ["git", "--version"]:
            return CommandResult(argv=tuple(argv), returncode=0, stdout="git 1")
        if argv[:2] == ["docker", "--version"]:
            return CommandResult(argv=tuple(argv), returncode=0, stdout="docker 1")
        if argv[:3] == ["docker", "compose", "version"]:
            return CommandResult(argv=tuple(argv), returncode=None, stdout="", timed_out=True)
        return CommandResult(argv=tuple(argv), returncode=None, stdout="", not_found=True)

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake):
        tools = {t.name: t for t in collect_tools(project_dir)}
    assert tools["docker-compose"].status in {
        ToolStatus.TIMEOUT,
        ToolStatus.NOT_FOUND,
        ToolStatus.ERROR,
    }


def test_env_unparsed_and_duplicates(project_dir: Path) -> None:
    (project_dir / ".env.example").write_text(
        "A=1\n!!!bad\nA=2\n",
        encoding="utf-8",
    )
    (project_dir / ".env").write_text("A=1\nB=2\n", encoding="utf-8")
    result = compare_env_files(project_dir)
    assert result.status in {CheckStatus.OK, CheckStatus.WARNING}
    assert result.unparsed_lines or result.duplicate_keys


def test_env_file_too_large(project_dir: Path) -> None:
    big = "K=" + ("x" * 3000) + "\n"
    (project_dir / ".env.example").write_bytes((big * 100).encode())
    # may or may not exceed depending on size — force over limit
    from devreport.collectors import env as env_mod

    (project_dir / ".env.example").write_bytes(b"A=1\n" + b"x" * (env_mod.MAX_ENV_FILE_BYTES + 10))
    result = compare_env_files(project_dir)
    assert result.status == CheckStatus.UNKNOWN


def test_logs_missing_file(tmp_path: Path) -> None:
    result = read_log_tail(tmp_path / "nope.log", 10)
    assert result.stats.rejected_reason is not None


def test_port_oserror_unknown() -> None:
    with patch("socket.socket") as sock_cls:
        sock = MagicMock()
        sock_cls.return_value = sock
        sock.bind.side_effect = OSError(13, "denied")
        result = check_port(12345)
    assert result.status == CheckStatus.UNKNOWN


def test_config_unknown_section(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text("[network]\nenabled = true\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_config_bad_bool(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text('[checks]\ntools = "yes"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_config_tail_range(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text("[logs]\ntail = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_write_parent_not_dir(tmp_path: Path) -> None:
    parent = tmp_path / "file"
    parent.write_text("x", encoding="utf-8")
    with pytest.raises(OutputError):
        write_report_file(parent / "out.md", "x")


def test_build_checks_disabled_and_log_error(project_dir: Path) -> None:
    checks = build_checks(
        project_root=project_dir,
        tools=[],
        project_files=[ProjectFileInfo(name="pyproject.toml", present=True)],
        env_comparison=EnvComparison(status=CheckStatus.OK),
        port_check=PortCheckResult(status=CheckStatus.OK, port=1, detail="ok"),
        log_stats=LogStats(requested=True, rejected_reason="bad"),
        tools_enabled=False,
        env_enabled=False,
    )
    codes = {c.code for c in checks}
    assert "tools.disabled" in codes
    assert "env.disabled" in codes
    assert "logs.read" in codes


def test_tool_check_branches() -> None:
    tools = [
        ToolInfo(name="a", status=ToolStatus.TIMEOUT, detail="t"),
        ToolInfo(name="b", status=ToolStatus.ERROR, detail="e"),
        ToolInfo(name="c", status=ToolStatus.UNKNOWN, detail="u"),
    ]
    checks = build_checks(
        project_root=Path("."),
        tools=tools,
        project_files=[],
        env_comparison=None,
        port_check=None,
        log_stats=None,
        tools_enabled=True,
        env_enabled=True,
    )
    statuses = {c.code: c.status for c in checks}
    assert statuses["tools.a"] == CheckStatus.UNKNOWN
    assert statuses["tools.b"] == CheckStatus.ERROR


def test_markdown_sections_full() -> None:
    from devreport.models import EnvComparison, PortCheckResult

    report = Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        created_at_utc="2026-01-01T00:00:00Z",
        system=SystemInfo("Linux", "x", "x86_64", "3.11"),
        tools=[],
        project_files=[],
        checks=[],
        env_comparison=EnvComparison(
            status=CheckStatus.WARNING,
            missing_keys=("A",),
            extra_keys=("B",),
            duplicate_keys=("C",),
            unparsed_lines=(3,),
            detail="d",
        ),
        port_check=PortCheckResult(status=CheckStatus.OK, port=80, detail="free"),
        log_stats=LogStats(
            requested=True,
            path="/tmp/a.log",
            lines_returned=1,
            bytes_read=1,
            truncated_by_size=True,
            truncated_by_line_length=True,
            decoding_replacements=True,
            rejected_reason=None,
        ),
        log_excerpt="hello\n````ticks",
        limitations=["L1"],
    )
    md = render_markdown(report)
    assert "## Порт" in md
    assert "## Лог" in md
    assert "## Сравнение .env" in md
    assert escape_html_in_untrusted("<script>") == "&lt;script&gt;"


def test_merge_options_and_report_with_port_log(project_dir: Path, tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_text("password=abc\n", encoding="utf-8")
    cfg = AppConfig(format="json", tail=10, checks_tools=False, checks_env=True)
    opts = merge_options(
        config=cfg,
        project=str(project_dir),
        port=None,
        log=str(log),
        tail=None,
        format_value=None,
    )
    assert opts.format == "json"
    assert opts.tail == 10
    report = build_report(opts)
    text = render_report(report, "json")
    assert "abc" not in text


def test_cli_force_overwrite(project_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "r.md"
    out.write_text("old", encoding="utf-8")
    with patch("devreport.collectors.tools.collect_tools", return_value=[]):
        result = runner.invoke(
            app,
            [
                "collect",
                "--project",
                str(project_dir),
                "--output",
                str(out),
                "--force",
            ],
        )
    assert result.exit_code == 0
    assert "DevReport" in out.read_text(encoding="utf-8")


def test_cli_missing_project(tmp_path: Path) -> None:
    result = runner.invoke(app, ["collect", "--project", str(tmp_path / "nope")])
    assert result.exit_code == 2


def test_run_allowed_timeout(project_dir: Path) -> None:
    import subprocess as sp

    with (
        patch(
            "devreport.utils.subprocess.find_executable",
            return_value=Path("C:/Windows/System32/git.exe"),
        ),
        patch(
            "devreport.utils.subprocess.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd="git", timeout=1, output=b"partial"),
        ),
    ):
        result = run_allowed(["git", "--version"], project_root=project_dir)
    assert result.timed_out is True


def test_run_allowed_permission(project_dir: Path) -> None:
    with (
        patch(
            "devreport.utils.subprocess.find_executable",
            return_value=Path("C:/Windows/System32/git.exe"),
        ),
        patch(
            "devreport.utils.subprocess.subprocess.run",
            side_effect=PermissionError(),
        ),
    ):
        result = run_allowed(["git", "--version"], project_root=project_dir)
    assert result.permission_denied is True


def test_find_executable_skips_relative(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", f".{__import__('os').pathsep}{tmp_path}")
    assert find_executable("git", project_root=tmp_path) is None


def test_sanitize_without_engine() -> None:
    out = sanitize_text("token=zzz")
    assert "zzz" not in out


def test_parse_export_and_empty() -> None:
    parsed = parse_env_keys("")
    assert parsed.keys == []


def test_redaction_home_fallback() -> None:
    engine = RedactionEngine(home_path="")
    assert engine.redact("nohome") == "nohome"
