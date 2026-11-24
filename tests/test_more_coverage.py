"""Ещё покрытие редких веток."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devreport.cli import app, run
from devreport.collectors.logs import read_log_tail
from devreport.collectors.system import collect_system_info
from devreport.config import ConfigError, load_config
from devreport.models import CheckStatus, ToolStatus
from devreport.service import CollectOptions, build_report
from devreport.utils.io import OutputError, write_report_file
from devreport.utils.paths import is_regular_file, resolve_project_path
from devreport.utils.subprocess import CommandResult, is_allowed_command, run_allowed

runner = CliRunner()


def test_main_entrypoint_import() -> None:
    from devreport.__main__ import main

    assert callable(main)
    assert callable(run)


def test_system_linux_name_only() -> None:
    with (
        patch("devreport.collectors.system.platform.system", return_value="Linux"),
        patch(
            "devreport.collectors.system.platform.freedesktop_os_release",
            return_value={"NAME": "Debian"},
        ),
    ):
        info = collect_system_info()
    assert "Debian" in info.os_release


def test_system_linux_fallback_error() -> None:
    with (
        patch("devreport.collectors.system.platform.system", return_value="Linux"),
        patch(
            "devreport.collectors.system.platform.freedesktop_os_release",
            side_effect=OSError("no"),
        ),
        patch("devreport.collectors.system.platform.release", return_value="6.1"),
        patch("devreport.collectors.system.platform.version", return_value=""),
    ):
        info = collect_system_info()
    assert info.os_release


def test_config_invalid_toml(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text("[[[[", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_config_report_not_table(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text("report = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_logs_not_file_device(tmp_path: Path) -> None:
    # На Windows нет простых FIFO — симулируем is_file False через mock
    path = tmp_path / "x"
    path.write_text("a", encoding="utf-8")
    with (
        patch.object(Path, "is_symlink", return_value=False),
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "is_dir", return_value=False),
        patch.object(Path, "is_file", return_value=False),
    ):
        result = read_log_tail(path, 5)
    assert result.stats.rejected_reason is not None


def test_write_directory_as_output(tmp_path: Path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    with pytest.raises(OutputError):
        write_report_file(d, "x", force=True)


def test_cli_invalid_format(project_dir: Path) -> None:
    result = runner.invoke(
        app,
        ["collect", "--project", str(project_dir), "--format", "xml"],
    )
    assert result.exit_code == 2


def test_cli_project_is_file(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["collect", "--project", str(f)])
    assert result.exit_code == 2


def test_build_report_with_port(project_dir: Path) -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    with patch("devreport.service.collect_tools", return_value=[]):
        report = build_report(
            CollectOptions(project=str(project_dir), port=port, tools_enabled=True)
        )
    assert report.port_check is not None
    assert report.port_check.status == CheckStatus.OK


def test_allowed_command_variants() -> None:
    import sys

    # .exe допускается только на Windows
    assert is_allowed_command("docker-compose.exe") is (sys.platform == "win32")
    assert not is_allowed_command("evil.bat")


def test_run_allowed_empty() -> None:
    result = run_allowed([])
    assert result.not_found is True


def test_run_allowed_oserror(project_dir: Path) -> None:
    with (
        patch(
            "devreport.utils.subprocess.find_executable",
            return_value=Path("C:/Windows/System32/git.exe"),
        ),
        patch(
            "devreport.utils.subprocess.subprocess.run",
            side_effect=OSError("boom"),
        ),
    ):
        result = run_allowed(["git", "--version"], project_root=project_dir)
    assert result.error_detail is not None


def test_resolve_relative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = resolve_project_path(".")
    assert p == tmp_path or p.resolve() == tmp_path.resolve()


def test_is_regular_file_missing(tmp_path: Path) -> None:
    assert is_regular_file(tmp_path / "missing") is False


def test_output_error_on_replace(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    with (
        patch("devreport.utils.io.os.replace", side_effect=OSError("fail")),
        pytest.raises(OutputError),
    ):
        write_report_file(target, "data", force=False)


def test_tools_compose_error_no_fallback_success(project_dir: Path) -> None:
    from devreport.collectors.tools import collect_tools

    def fake(argv: list[str], **kwargs: object) -> CommandResult:
        if argv[:2] == ["git", "--version"]:
            return CommandResult(argv=tuple(argv), returncode=0, stdout="git 1")
        if argv[:2] == ["docker", "--version"]:
            return CommandResult(argv=tuple(argv), returncode=0, stdout="docker 1")
        if argv[:3] == ["docker", "compose", "version"]:
            return CommandResult(argv=tuple(argv), returncode=125, stdout="")
        if argv[:2] == ["docker-compose", "--version"]:
            return CommandResult(
                argv=tuple(argv),
                returncode=None,
                stdout="",
                not_found=True,
            )
        return CommandResult(argv=tuple(argv), returncode=None, stdout="", not_found=True)

    with patch("devreport.collectors.tools.run_allowed", side_effect=fake):
        tools = {t.name: t for t in collect_tools(project_dir)}
    assert tools["docker-compose"].status == ToolStatus.ERROR
