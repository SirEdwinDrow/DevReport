"""Тесты сравнения .env."""

from __future__ import annotations

from pathlib import Path

from devreport.collectors.env import compare_env_files, parse_env_keys
from devreport.models import CheckStatus


def test_parse_simple_keys() -> None:
    text = "# comment\nFOO=1\nexport BAR=2\nBAZ=\nnot a line\nFOO=dup\n"
    parsed = parse_env_keys(text)
    assert parsed.keys == ["FOO", "BAR", "BAZ"]
    assert "FOO" in parsed.duplicates
    assert parsed.unparsed_lines == [5]


def test_env_example_missing_skipped(project_dir: Path) -> None:
    result = compare_env_files(project_dir)
    assert result.status == CheckStatus.SKIPPED


def test_env_missing_warning(project_dir: Path) -> None:
    (project_dir / ".env.example").write_text("A=1\nB=2\n", encoding="utf-8")
    result = compare_env_files(project_dir)
    assert result.status == CheckStatus.WARNING
    assert result.missing_keys == ("A", "B")


def test_env_compare_ok_and_extra(sample_env_pair: Path) -> None:
    result = compare_env_files(sample_env_pair)
    assert result.status == CheckStatus.WARNING  # missing SECRET_KEY
    assert "SECRET_KEY" in result.missing_keys
    assert "EXTRA" in result.extra_keys
    # Значения не должны попасть в detail как секреты БД
    blob = str(result)
    assert "postgres://u:p@localhost/db" not in blob


def test_env_symlink_rejected(project_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "real.env.example"
    target.write_text("A=1\n", encoding="utf-8")
    link = project_dir / ".env.example"
    try:
        link.symlink_to(target)
    except OSError:
        # Windows без привилегий — пропускаем
        return
    result = compare_env_files(project_dir)
    assert result.status == CheckStatus.UNKNOWN
