"""Тесты движка маскирования."""

from __future__ import annotations

from pathlib import Path

from devreport.redaction.engine import SECRET_LABEL, RedactionEngine, sanitize_text


def test_password_and_token_redacted() -> None:
    engine = RedactionEngine(home_path="/home/user")
    text = "password=supersecret token=abc123 api_key=xyz"
    out = engine.redact(text)
    assert "supersecret" not in out
    assert "abc123" not in out
    assert "xyz" not in out
    assert SECRET_LABEL in out


def test_compound_secret_keys_redacted() -> None:
    engine = RedactionEngine()
    text = (
        "client_secret=should_this_redact "
        "AWS_SECRET_ACCESS_KEY=aka_secret_value "
        "access_token=tok_abc "
        "db_password=hunter2 "
        "my-api-key=key123"
    )
    out = engine.redact(text)
    assert "should_this_redact" not in out
    assert "aka_secret_value" not in out
    assert "tok_abc" not in out
    assert "hunter2" not in out
    assert "key123" not in out
    assert SECRET_LABEL in out


def test_export_setx_json_yaml_patterns() -> None:
    engine = RedactionEngine()
    samples = [
        "export CLIENT_SECRET=exp_value_here",
        "setx AWS_SECRET_ACCESS_KEY aka_setx_value_here",
        'setx db_password "quoted_setx_secret"',
        '{"client_secret":"json_secret_value","n":1}',
        '"api_key": "json_api_key_value"',
        "client_secret: yaml_secret_value",
        "access_token: 'yaml_quoted_token'",
    ]
    for sample in samples:
        out = engine.redact(sample)
        assert SECRET_LABEL in out, sample
        for leak in (
            "exp_value_here",
            "aka_setx_value_here",
            "quoted_setx_secret",
            "json_secret_value",
            "json_api_key_value",
            "yaml_secret_value",
            "yaml_quoted_token",
        ):
            if leak in sample:
                assert leak not in out, sample


def test_bearer_without_authorization_header() -> None:
    engine = RedactionEngine()
    fake_jwt = "eyJ_TEST_NOT_A_REAL.aa.bb"
    out = engine.redact(f"token response Bearer {fake_jwt}")
    assert fake_jwt not in out
    assert SECRET_LABEL in out


def test_token_prefixes_and_base64_near_key() -> None:
    engine = RedactionEngine()
    b64 = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo="  # 32+ chars base64-ish
    text = f"sk_test_fictionOnlyToken123 ghp_TESTNOTAREALPAT0001 secret {b64}"
    out = engine.redact(text)
    assert "sk_test_fictionOnlyToken123" not in out
    assert "ghp_TESTNOTAREALPAT0001" not in out
    assert b64 not in out
    assert "secret [REDACTED_SECRET]=" not in out
    assert f"secret {SECRET_LABEL}" in out
    assert SECRET_LABEL in out


def test_negative_benign_not_redacted() -> None:
    engine = RedactionEngine()
    benign_cases = [
        "secretary=Alice",
        "secretarial_pool=12",
        "tokenize_count=3",
        "short secret abc",  # base64-near слишком короткий
        "hello world without secrets",
    ]
    for sample in benign_cases:
        out = engine.redact(sample)
        # Значения/текст не должны подменяться SECRET_LABEL целиком без причины
        if "secretary=Alice" in sample:
            assert "Alice" in out
            assert SECRET_LABEL not in out
        if "hello world" in sample:
            assert out == sample
        if "short secret abc" in sample:
            assert "abc" in out


def test_shared_engine_aliases_stable_across_sections() -> None:
    """Один engine → одинаковые EMAIL/IP/HOME across разных полей отчёта."""
    from devreport import SCHEMA_VERSION, __version__
    from devreport.models import (
        CheckResult,
        CheckStatus,
        LogStats,
        Report,
        SystemInfo,
    )
    from devreport.renderers.json import render_json
    from devreport.renderers.markdown import render_markdown

    home = "/home/stableuser"
    engine = RedactionEngine(home_path=home)
    report = Report(
        schema_version=SCHEMA_VERSION,
        tool_version=__version__,
        created_at_utc="2026-01-01T00:00:00Z",
        system=SystemInfo("Linux", "x", "x86_64", "3.11"),
        checks=[
            CheckResult(
                code="demo.contact",
                status=CheckStatus.WARNING,
                title="contact",
                description=f"write to user@example.com from {home}/notes",
            )
        ],
        log_stats=LogStats(
            requested=True,
            path=f"{home}/app.log",
            lines_returned=1,
            bytes_read=40,
        ),
        log_excerpt="alert user@example.com at 10.0.0.5",
        limitations=["L"],
    )
    md = render_markdown(report, engine)
    # Тот же engine для JSON — псевдонимы не сбрасываются
    js = render_json(report, engine)
    assert "user@example.com" not in md and "user@example.com" not in js
    assert home not in md and home not in js
    assert md.count("EMAIL_001") >= 1
    assert js.count("EMAIL_001") >= 1
    # Один email → один псевдоним во всём прогоне
    assert "EMAIL_002" not in md
    assert "EMAIL_002" not in js
    assert "HOME_001" in md and "HOME_001" in js
    assert "IP_001" in md or "IP_001" in js


def test_bearer_basic_jwt() -> None:
    engine = RedactionEngine()
    jwt = "eyJ_TEST_HEADER.eyJ_TEST_PAYLOAD.TEST_SIGNATURE"
    text = f"Authorization: Bearer {jwt}\nAuthorization: Basic dXNlcjpwYXNz"
    out = engine.redact(text)
    assert jwt not in out
    assert "dXNlcjpwYXNz" not in out
    assert SECRET_LABEL in out


def test_email_ip_aliases_stable() -> None:
    engine = RedactionEngine()
    text = "user@example.com from 10.0.0.1 and again user@example.com 10.0.0.1"
    out = engine.redact(text)
    assert "user@example.com" not in out
    assert "10.0.0.1" not in out
    assert out.count("EMAIL_001") == 2
    assert out.count("IP_001") == 2


def test_home_path_redacted(tmp_path: Path) -> None:
    home = str(tmp_path / "homeuser")
    engine = RedactionEngine(home_path=home)
    out = engine.redact(f"log at {home}/.ssh/id_rsa")
    assert home not in out
    assert "HOME_001" in out


def test_url_credentials() -> None:
    engine = RedactionEngine()
    out = engine.redact("https://alice:wonderland@example.com/x")
    assert "alice" not in out
    assert "wonderland" not in out
    assert SECRET_LABEL in out


def test_mapping_not_in_sanitize_output() -> None:
    engine = RedactionEngine()
    out = sanitize_text("mail me at a@b.co from 8.8.8.8", engine)
    assert "a@b.co" not in out
    assert engine.mapping_size() >= 2
    # Таблица не сериализуется в строку результата
    assert "_email_map" not in out


def test_ansi_and_controls_stripped() -> None:
    raw = "ok\x1b[31mRED\x1b[0m\x00secret"
    out = sanitize_text(raw)
    assert "\x1b" not in out
    assert "\x00" not in out
    assert "RED" in out


def test_render_report_uses_single_engine_for_log(tmp_path: Path, project_dir: Path) -> None:
    from unittest.mock import patch

    from devreport.service import CollectOptions, build_report, render_report

    log = tmp_path / "app.log"
    log.write_text(
        "client_secret=should_this_redact\n"
        "AWS_SECRET_ACCESS_KEY=aka_secret_value\n"
        "mail user@example.com user@example.com\n",
        encoding="utf-8",
    )
    with patch("devreport.service.collect_tools", return_value=[]):
        report = build_report(
            CollectOptions(
                project=str(project_dir),
                log=str(log),
                tools_enabled=True,
            )
        )
    # До сериализации excerpt ещё сырой (граница — render)
    assert report.log_excerpt is not None
    assert "should_this_redact" in report.log_excerpt

    out = render_report(report, "json")
    assert "should_this_redact" not in out
    assert "aka_secret_value" not in out
    assert "user@example.com" not in out
    assert out.count("EMAIL_001") >= 2
    assert "EMAIL_002" not in out
