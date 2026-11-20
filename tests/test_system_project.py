"""Тесты system/project collectors и service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from devreport.collectors.project import collect_project_files
from devreport.collectors.system import collect_system_info
from devreport.service import CollectOptions, build_report, render_report


def test_system_info_fields() -> None:
    info = collect_system_info()
    assert info.os_family
    assert info.architecture
    assert info.python_version
    # Не должны утечь hostname-like поля в dataclass
    assert not hasattr(info, "hostname")


def test_project_files(project_dir: Path) -> None:
    (project_dir / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project_dir / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    files = {f.name: f.present for f in collect_project_files(project_dir)}
    assert files["pyproject.toml"] is True
    assert files["Dockerfile"] is True
    assert files["package.json"] is False


def test_build_report_empty(project_dir: Path) -> None:
    with patch("devreport.service.collect_tools", return_value=[]):
        report = build_report(CollectOptions(project=str(project_dir), tools_enabled=True))
    assert report.schema_version
    md = render_report(report, "markdown")
    js = render_report(report, "json")
    assert "DevReport" in md
    assert "schema_version" in js
