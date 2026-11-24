"""Тесты безопасного subprocess."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from devreport.utils.subprocess import find_executable, is_allowed_command, run_allowed


def test_allowlist() -> None:
    assert is_allowed_command("git")
    assert is_allowed_command("docker")
    assert is_allowed_command("docker-compose")
    assert not is_allowed_command("python")
    assert not is_allowed_command("curl")
    # Суффикс .exe допускается только на Windows
    assert is_allowed_command("docker.exe") is (sys.platform == "win32")


def test_allowlist_rejects_arbitrary_suffixes() -> None:
    # Раньше матчинг по stem пропускал git.foo/git.sh/git.com — регрессия
    for name in (
        "git.foo",
        "git.sh",
        "git.com",
        "git.bat",
        "git.cmd",
        "docker-compose.sh",
        "git.py",
    ):
        assert not is_allowed_command(name), name


def test_refuses_non_allowlist(project_dir: Path) -> None:
    result = run_allowed(["python", "--version"], project_root=project_dir)
    assert result.not_found is True


def test_excludes_project_path(project_dir: Path, monkeypatch: object) -> None:
    fake_bin = project_dir / "git.exe"
    fake_bin.write_text("", encoding="utf-8")
    # PATH содержит project
    monkeypatch.setenv("PATH", str(project_dir))  # type: ignore[attr-defined]
    found = find_executable("git", project_root=project_dir)
    assert found is None


def test_run_file_not_found(project_dir: Path) -> None:
    with (
        patch(
            "devreport.utils.subprocess.find_executable",
            return_value=Path("/nonexistent/git"),
        ),
        patch(
            "devreport.utils.subprocess.subprocess.run",
            side_effect=FileNotFoundError(),
        ),
    ):
        result = run_allowed(["git", "--version"], project_root=project_dir)
    assert result.not_found is True
