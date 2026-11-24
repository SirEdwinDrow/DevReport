"""Smoke-тесты через реальный subprocess python -m."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _cp1252_env() -> dict[str, str]:
    """Симулировать Windows-консоль без UTF-8: кириллица в help/сводке не должна падать."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    return env


def test_module_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "devreport", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=_cp1252_env(),
    )
    assert proc.returncode == 0, proc.stderr
    assert "collect" in proc.stdout.lower() or "collect" in proc.stderr.lower()


def test_module_version() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "devreport", "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=_cp1252_env(),
    )
    assert proc.returncode == 0, proc.stderr
    assert "devreport" in (proc.stdout + proc.stderr).lower()


def test_collect_in_tmp(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "devreport",
            "collect",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(tmp_path),
        env=_cp1252_env(),
    )
    assert proc.returncode == 0, proc.stderr
    assert '"schema_version"' in proc.stdout
