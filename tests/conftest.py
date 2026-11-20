"""Общие фикстуры тестов DevReport."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def sample_env_pair(project_dir: Path) -> Path:
    (project_dir / ".env.example").write_text(
        "APP_NAME=demo\nDATABASE_URL=\nSECRET_KEY=\n",
        encoding="utf-8",
    )
    (project_dir / ".env").write_text(
        "APP_NAME=demo\nDATABASE_URL=postgres://u:p@localhost/db\nEXTRA=1\n",
        encoding="utf-8",
    )
    return project_dir
