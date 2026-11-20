"""Тесты рендереров Markdown/JSON."""

from __future__ import annotations

import json

from devreport import SCHEMA_VERSION, __version__
from devreport.models import (
    CheckResult,
    CheckStatus,
    LogStats,
    ProjectFileInfo,
    Report,
    SystemInfo,
    ToolInfo,
    ToolStatus,
)
from devreport.renderers.json import render_json
from devreport.renderers.markdown import render_markdown


def _sample_report() -> Report:
    return Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        created_at_utc="2026-01-01T00:00:00Z",
        system=SystemInfo(
            os_family="Windows",
            os_release="10",
            architecture="AMD64",
            python_version="3.11.0",
        ),
        tools=[ToolInfo(name="git", status=ToolStatus.FOUND, version="git 2")],
        project_files=[ProjectFileInfo(name=".env", present=False)],
        checks=[
            CheckResult(
                code="tools.git",
                status=CheckStatus.OK,
                title="git",
                description="ok",
            )
        ],
        log_stats=LogStats(requested=True, path="app.log", lines_returned=2, bytes_read=10),
        log_excerpt="password=leak password=leak\n```\nevil",
        limitations=["test limitation"],
    )


def test_json_and_markdown_share_codes() -> None:
    report = _sample_report()
    md = render_markdown(report)
    data = json.loads(render_json(report))
    assert "tools.git" in md
    assert any(c["code"] == "tools.git" for c in data["checks"])
    assert data["schema_version"] == SCHEMA_VERSION
    assert "leak" not in md
    assert "leak" not in render_json(report)


def test_markdown_safe_fence() -> None:
    report = _sample_report()
    md = render_markdown(report)
    assert "```" in md or "````" in md
    assert report.privacy_warning.split(".")[0] in md or "маскирование" in md.lower()
