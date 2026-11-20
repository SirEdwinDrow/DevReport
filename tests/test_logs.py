"""Тесты чтения логов."""

from __future__ import annotations

from pathlib import Path

from devreport.collectors.logs import MAX_LOG_BYTES, read_log_tail


def test_read_tail_lines(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text("\n".join(f"line-{i}" for i in range(100)), encoding="utf-8")
    result = read_log_tail(log, 5)
    assert result.stats.rejected_reason is None
    assert result.stats.lines_returned == 5
    assert result.lines[-1] == "line-99"


def test_reject_directory(tmp_path: Path) -> None:
    result = read_log_tail(tmp_path, 10)
    assert result.stats.rejected_reason is not None


def test_reject_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real.log"
    real.write_text("a\n", encoding="utf-8")
    link = tmp_path / "link.log"
    try:
        link.symlink_to(real)
    except OSError:
        return
    result = read_log_tail(link, 10)
    assert result.stats.rejected_reason is not None
    assert "symlink" in result.stats.rejected_reason.lower()


def test_large_file_truncated(tmp_path: Path) -> None:
    log = tmp_path / "big.log"
    # Пишем чуть больше лимита
    chunk = b"x" * 1024 + b"\n"
    repeats = (MAX_LOG_BYTES // len(chunk)) + 5
    with log.open("wb") as handle:
        for i in range(repeats):
            handle.write(f"{i}-".encode() + chunk)
    result = read_log_tail(log, 3)
    assert result.stats.truncated_by_size is True
    assert result.stats.lines_returned <= 3


def test_invalid_tail(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_text("a\n", encoding="utf-8")
    result = read_log_tail(log, 0)
    assert result.stats.rejected_reason is not None


def test_long_line_truncated(tmp_path: Path) -> None:
    log = tmp_path / "long.log"
    log.write_text("y" * 10000, encoding="utf-8")
    result = read_log_tail(log, 1)
    assert result.stats.truncated_by_line_length is True
    assert result.lines[0].endswith("…")
