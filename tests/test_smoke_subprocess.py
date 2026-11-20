"""Smoke-тесты через реальный subprocess python -m."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_module_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "devreport", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "collect" in proc.stdout.lower() or "collect" in proc.stderr.lower()


def test_module_version() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "devreport", "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
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
    )
    assert proc.returncode == 0
    assert '"schema_version"' in proc.stdout
