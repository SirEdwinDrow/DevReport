"""Тесты конфигурации."""

from __future__ import annotations

from pathlib import Path

import pytest

from devreport.config import ConfigError, load_config


def test_default_when_missing(project_dir: Path) -> None:
    cfg = load_config(project_dir)
    assert cfg.format == "markdown"
    assert cfg.tail == 50
    assert cfg.checks_tools is True


def test_load_valid(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text(
        '[report]\nformat = "json"\n[logs]\ntail = 20\n[checks]\ntools = false\nenv = true\n',
        encoding="utf-8",
    )
    cfg = load_config(project_dir)
    assert cfg.format == "json"
    assert cfg.tail == 20
    assert cfg.checks_tools is False


def test_unknown_key(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text(
        '[report]\nformat = "markdown"\nunknown = 1\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_bad_type(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text(
        '[logs]\ntail = "many"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_symlink_rejected(project_dir: Path, tmp_path: Path) -> None:
    real = tmp_path / "cfg.toml"
    real.write_text('[report]\nformat = "json"\n', encoding="utf-8")
    link = project_dir / ".devreport.toml"
    try:
        link.symlink_to(real)
    except OSError:
        return
    with pytest.raises(ConfigError):
        load_config(project_dir)


def test_forbidden_output_key(project_dir: Path) -> None:
    (project_dir / ".devreport.toml").write_text(
        '[report]\nformat = "markdown"\noutput = "x.md"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(project_dir)
