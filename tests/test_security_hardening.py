"""Регрессионные тесты security-hardening: redaction, allowlist, dotenv-лог."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from devreport.redaction.engine import (
    SECRET_LABEL,
    RedactionEngine,
    is_dotenv_log_path,
    mask_dotenv_text,
)


@pytest.mark.parametrize(
    "secret",
    [
        "AKIAIOSFODNN7EXAMPLE",  # AWS access key id
        "ASIAIOSFODNN7EXAMPLE",  # AWS temporary
        "sk-ant-api03-aaaabbbbccccddddeeee",
        "sk-proj-aaaabbbbccccddddeeeeffff",
        "sk-aaaabbbbccccddddeeeeffffgggg",
        "glpat-aaaabbbbccccdddd1234",
        "AIzaSyAaaabbbbccccddddeeeeffffgggg00001",
        "ya29.a0AfH6SMBaaaabbbbcccc",
        "hf_aaaabbbbccccddddeeeeffffgggghh",
    ],
)
def test_token_prefixes_masked(secret: str) -> None:
    out = RedactionEngine().redact(f"leak {secret} end")
    assert secret not in out
    assert SECRET_LABEL in out


@pytest.mark.parametrize(
    "key",
    [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "X-Auth-Token",
        "private_key",
        "pwd",
        "passphrase",
        "api_key",
        "credentials",
    ],
)
def test_selective_secret_key_vocab(key: str) -> None:
    out = RedactionEngine().redact(f"{key}=supersecretvalue123")
    assert "supersecretvalue123" not in out
    assert SECRET_LABEL in out


def test_wide_vocab_segments_not_overmasked() -> None:
    """Голые key/session/signature/pass не должны массово маскировать логи."""
    engine = RedactionEngine()
    for sample in (
        "key=visible_config_value",
        "session=user_session_name",
        "signature=checksum_abc",
        "pass=true",
        "cookie=theme_dark",
    ):
        out = engine.redact(sample)
        # Значение остаётся — сегмент не в словаре
        assert SECRET_LABEL not in out, sample


def test_single_quoted_json_redacted() -> None:
    out = RedactionEngine().redact("{'api_key': 'single_quoted_secret'}")
    assert "single_quoted_secret" not in out
    assert "'api_key'" in out


def test_authorization_header_any_scheme() -> None:
    out = RedactionEngine().redact(
        'Authorization: Digest username="u", nonce="n", response="deadbeef"\n'
        "Proxy-Authorization: NTLM TlRMTVNTUAABAAAA\n"
        "Authorization: Bearer tok123"
    )
    assert "deadbeef" not in out
    assert "TlRMTVNTUAABAAAA" not in out
    assert "tok123" not in out
    assert "Authorization:" in out


def test_cookie_headers_masked() -> None:
    out = RedactionEngine().redact("Set-Cookie: session=abcdef123; HttpOnly\nCookie: a=1; b=2")
    assert "abcdef123" not in out
    assert "a=1" not in out


def test_pem_block_masked_incomplete_tail() -> None:
    pem = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU=\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    out = RedactionEngine().redact(f"pre {pem} post")
    assert "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU" not in out
    # Хвост без END-маркера тоже маскируется до конца текста
    truncated = pem.rsplit("\n", 1)[0]
    out2 = RedactionEngine().redact(f"pre {truncated}")
    assert "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU" not in out2


def test_secret_kv_value_masked_to_end_of_line() -> None:
    """EOL-маскирование только для secret-like ключей."""
    out = RedactionEngine().redact("passphrase=my secret words rest")
    assert "my secret words" not in out
    assert f"passphrase={SECRET_LABEL}" in out


def test_mask_dotenv_text_all_values() -> None:
    text = "APP_NAME=demo\nMY_VENDOR_SECRET=supersecret\n# COMMENTED_KEY=alsosensitive\nEMPTY_OK=\n"
    out = mask_dotenv_text(text)
    assert "supersecret" not in out
    assert "alsosensitive" not in out
    assert f"MY_VENDOR_SECRET={SECRET_LABEL}" in out
    assert "EMPTY_OK=" in out


def test_is_dotenv_log_path() -> None:
    assert is_dotenv_log_path(".env")
    assert is_dotenv_log_path("/tmp/.env.production")
    assert is_dotenv_log_path(Path("C:/x/.ENV.local"))
    assert not is_dotenv_log_path("app.log")
    assert not is_dotenv_log_path(None)


def test_env_log_masked_at_render_boundary(tmp_path: Path, project_dir: Path) -> None:
    """--log на .env-файл: значения любых ключей маскируются при render."""
    from devreport.service import CollectOptions, build_report, render_report

    env_file = tmp_path / ".env.production"
    env_file.write_text("MY_CUSTOM_CREDENTIAL=unique_secret_xyz\nAPP_NAME=demo\n", encoding="utf-8")
    with patch("devreport.service.collect_tools", return_value=[]):
        report = build_report(
            CollectOptions(project=str(project_dir), log=str(env_file), tools_enabled=True)
        )
    # Сырой excerpt ещё содержит значение — граница маскирования при render
    assert report.log_excerpt is not None
    assert "unique_secret_xyz" in report.log_excerpt

    out = render_report(report, "json")
    assert "unique_secret_xyz" not in out
    assert "MY_CUSTOM_CREDENTIAL" in out  # имя ключа остаётся видимым


def test_regular_log_not_dotenv_masked(project_dir: Path, tmp_path: Path) -> None:
    """Обычный лог: нестандартные ключи не маскируются (документированный лимит)."""
    from devreport.service import CollectOptions, build_report, render_report

    log = tmp_path / "app.log"
    log.write_text("CUSTOM_FIELD=visible_value\n", encoding="utf-8")
    with patch("devreport.service.collect_tools", return_value=[]):
        report = build_report(
            CollectOptions(project=str(project_dir), log=str(log), tools_enabled=True)
        )
    out = render_report(report, "json")
    assert "visible_value" in out


def test_run_allowed_rejects_explicit_symlink(project_dir: Path, tmp_path: Path) -> None:
    """Явный путь к исполняемому: symlink отклоняется как не-файл."""
    if sys.platform == "win32":
        pytest.skip("symlink на Windows требует привилегий")
    from devreport.utils.subprocess import run_allowed

    real = tmp_path / "real_git"
    real.write_text("#!/bin/sh\n", encoding="utf-8")
    # basename git разрешён, но путь — через symlink
    link_dir = tmp_path / "bin"
    link_dir.mkdir()
    link = link_dir / "git"
    link.symlink_to(real)
    result = run_allowed([str(link), "--version"], project_root=project_dir)
    assert result.not_found is True
    assert result.error_detail == "not a regular file or symlink"


def test_run_allowed_explicit_path_regular(project_dir: Path, tmp_path: Path) -> None:
    """Явный путь git вне проекта: обычный файл проходит до запуска."""
    if sys.platform == "win32":
        pytest.skip("chmod/executable semantics только POSIX")
    from devreport.utils.subprocess import run_allowed

    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\necho fake git version 9.9\n", encoding="utf-8")
    fake.chmod(0o755)
    result = run_allowed([str(fake), "--version"], project_root=project_dir)
    assert result.returncode == 0
    assert "fake git" in result.stdout


def test_find_executable_rejects_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Своё улучшение: symlink в PATH не считается допустимым executable."""
    if sys.platform == "win32":
        pytest.skip("symlink на Windows требует привилегий")
    from devreport.utils.subprocess import find_executable

    real = tmp_path / "real_git"
    real.write_text("#!/bin/sh\n", encoding="utf-8")
    real.chmod(0o755)
    bin_dir = tmp_path / "pathbin"
    bin_dir.mkdir()
    link = bin_dir / "git"
    link.symlink_to(real)
    monkeypatch.setenv("PATH", str(bin_dir))
    assert find_executable("git", project_root=tmp_path / "proj") is None


def test_open_regular_file_rejects_symlink(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("symlink на Windows требует привилегий")
    from devreport.utils.paths import open_regular_file

    real = tmp_path / "real.log"
    real.write_text("x", encoding="utf-8")
    link = tmp_path / "link.log"
    link.symlink_to(real)
    with pytest.raises(OSError):
        open_regular_file(link)


def test_markdown_escapes_html_in_external_fields() -> None:
    from devreport import SCHEMA_VERSION, __version__
    from devreport.models import Report, SystemInfo, ToolInfo, ToolStatus
    from devreport.renderers.markdown import render_markdown

    report = Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        created_at_utc="2026-01-01T00:00:00Z",
        system=SystemInfo("Linux", "<b>x</b>", "x86_64", "3.11"),
        tools=[
            ToolInfo(
                name="git",
                status=ToolStatus.FOUND,
                version="1.0",
                detail="<script>alert(1)</script>",
            )
        ],
        limitations=["L"],
    )
    md = render_markdown(report)
    assert "<script>" not in md
    assert "&lt;script&gt;" in md
    assert "&lt;b&gt;x&lt;/b&gt;" in md
