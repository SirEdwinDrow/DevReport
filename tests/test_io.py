"""Тесты безопасной записи отчёта."""

from __future__ import annotations

from pathlib import Path

import pytest

from devreport.utils.io import OutputError, write_report_file


def test_write_new_file(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    write_report_file(target, "# hi\n", force=False)
    assert target.read_text(encoding="utf-8") == "# hi\n"


def test_no_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(OutputError):
        write_report_file(target, "new", force=False)
    assert target.read_text(encoding="utf-8") == "old"


def test_overwrite_with_force(tmp_path: Path) -> None:
    target = tmp_path / "report.md"
    target.write_text("old", encoding="utf-8")
    write_report_file(target, "new", force=True)
    assert target.read_text(encoding="utf-8") == "new"


def test_missing_parent(tmp_path: Path) -> None:
    target = tmp_path / "missing" / "report.md"
    with pytest.raises(OutputError):
        write_report_file(target, "x", force=False)


def test_reject_symlink_output(tmp_path: Path) -> None:
    real = tmp_path / "real.md"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        link.symlink_to(real)
    except OSError:
        return
    with pytest.raises(OutputError):
        write_report_file(link, "y", force=True)
