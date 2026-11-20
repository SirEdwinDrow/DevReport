"""Движок маскирования чувствительных данных."""

from __future__ import annotations

import os
import re
from pathlib import Path

SECRET_LABEL = "[REDACTED_SECRET]"

# Ключ: точное имя или составное (*_secret, *_token, AWS_SECRET_ACCESS_KEY, …).
# «secretary» не матчится: секретный сегмент только как целое слово/сегмент по _/-.
_SECRET_KEY = (
    r"(?:"
    r"password|passwd|token|secret|api[_-]?key|"
    r"[A-Za-z_][A-Za-z0-9]*[_-](?:password|passwd|token|secret|api[_-]?key)"
    r"(?:[_-][A-Za-z0-9_.-]+)?|"
    r"(?:password|passwd|token|secret|api[_-]?key)[_-][A-Za-z0-9_.-]+"
    r")"
)

_VALUE = r"(?:[^\s,;\"']+|\"[^\"]*\"|'[^']*')"

# KEY=value / KEY: value (dotenv, YAML scalar, shell)
_SECRET_KV = re.compile(rf"(?i)\b({_SECRET_KEY})(\s*[:=]\s*)({_VALUE})")

# JSON: "client_secret": "…" / "api_key":"…"
_SECRET_JSON = re.compile(
    rf'(?i)(")({_SECRET_KEY})("\s*:\s*)("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[^\s,}}\]]+)'
)

# Windows setx NAME value
_SETX = re.compile(rf"(?i)\b(setx\s+)({_SECRET_KEY})(\s+)({_VALUE})")

# export/set уже покрываются _SECRET_KV на KEY=value; дополнительно:
# setx выше; shell `export KEY=value` — через KV.

_BEARER = re.compile(r"(?i)((?:Authorization:\s*)?Bearer\s+)\S+")
_BASIC = re.compile(r"(?i)((?:Authorization:\s*)?Basic\s+)\S+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

# Высокоуверенные префиксы токенов (низкий FP)
_TOKEN_PREFIX = re.compile(
    r"\b("
    r"sk_live_[A-Za-z0-9]+|"
    r"sk_test_[A-Za-z0-9]+|"
    r"rk_live_[A-Za-z0-9]+|"
    r"pk_live_[A-Za-z0-9]+|"
    r"ghp_[A-Za-z0-9]+|"
    r"gho_[A-Za-z0-9]+|"
    r"github_pat_[A-Za-z0-9_]+|"
    r"xox[bprs]-[A-Za-z0-9-]+"
    r")\b"
)

# Base64-подобное значение рядом с известным ключом (без =): `secret AbCd...==`
# Только длинные (≥24) строки [A-Za-z0-9+/]+ с опциональным padding — снижает FP.
_SECRET_BASE64_NEAR = re.compile(
    rf"(?i)\b({_SECRET_KEY})(\s+)([A-Za-z0-9+/]{{24,}}={{0,2}})(?![A-Za-z0-9+/=])"
)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)
_URL_CREDS = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/\s:@]+):([^/\s@]+)@")

# ANSI CSI / OSC
_ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|].*?(?:\x07|\x1b\\)|[@-Z\\-_])")
# Опасные управляющие символы (кроме \t \n \r)
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class RedactionEngine:
    """Stateful redaction: одинаковые значения → одинаковые псевдонимы."""

    def __init__(self, home_path: str | None = None) -> None:
        self._email_map: dict[str, str] = {}
        self._ip_map: dict[str, str] = {}
        self._home_map: dict[str, str] = {}
        self._email_n = 0
        self._ip_n = 0
        self._home_n = 0
        if home_path is None:
            try:
                home_path = str(Path.home())
            except (RuntimeError, OSError):
                home_path = os.path.expanduser("~")
        self._home_path = home_path.rstrip("\\/") if home_path else ""

    def _alias(self, store: dict[str, str], value: str, prefix: str, counter_attr: str) -> str:
        key = value.lower() if prefix == "EMAIL" else value
        if key not in store:
            n = getattr(self, counter_attr) + 1
            setattr(self, counter_attr, n)
            store[key] = f"{prefix}_{n:03d}"
        return store[key]

    def redact(self, text: str) -> str:
        if not text:
            return text

        result = text

        # Сначала URL credentials
        result = _URL_CREDS.sub(rf"\1{SECRET_LABEL}:{SECRET_LABEL}@", result)

        def _kv_sub(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}{SECRET_LABEL}"

        result = _SECRET_KV.sub(_kv_sub, result)

        def _json_sub(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}{match.group(3)}{SECRET_LABEL}"

        result = _SECRET_JSON.sub(_json_sub, result)

        def _setx_sub(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}{match.group(3)}{SECRET_LABEL}"

        result = _SETX.sub(_setx_sub, result)

        def _b64_near_sub(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}{SECRET_LABEL}"

        result = _SECRET_BASE64_NEAR.sub(_b64_near_sub, result)

        result = _BEARER.sub(rf"\1{SECRET_LABEL}", result)
        result = _BASIC.sub(rf"\1{SECRET_LABEL}", result)
        result = _JWT.sub(SECRET_LABEL, result)
        result = _TOKEN_PREFIX.sub(SECRET_LABEL, result)

        def _email_sub(match: re.Match[str]) -> str:
            return self._alias(self._email_map, match.group(0), "EMAIL", "_email_n")

        result = _EMAIL.sub(_email_sub, result)

        def _ip_sub(match: re.Match[str]) -> str:
            return self._alias(self._ip_map, match.group(0), "IP", "_ip_n")

        result = _IPV4.sub(_ip_sub, result)

        if self._home_path:
            # Заменяем home path (и с / и с \)
            variants = {self._home_path}
            variants.add(self._home_path.replace("\\", "/"))
            variants.add(self._home_path.replace("/", "\\"))
            for home in sorted(variants, key=len, reverse=True):
                if home and home in result:
                    alias = self._alias(self._home_map, self._home_path, "HOME", "_home_n")
                    result = result.replace(home, alias)

        return result

    def mapping_size(self) -> int:
        """Размер таблицы соответствий (только для тестов; не сериализуется)."""
        return len(self._email_map) + len(self._ip_map) + len(self._home_map)


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def neutralize_controls(text: str) -> str:
    return _CTRL.sub("", text)


def sanitize_text(text: str, engine: RedactionEngine | None = None) -> str:
    """Общая граница санитарной обработки перед сериализацией."""
    if not text:
        return text
    cleaned = strip_ansi(text)
    cleaned = neutralize_controls(cleaned)
    if engine is None:
        engine = RedactionEngine()
    return engine.redact(cleaned)
