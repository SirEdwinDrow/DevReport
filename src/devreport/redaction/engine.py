"""Движок маскирования чувствительных данных."""

from __future__ import annotations

import os
import re
from pathlib import Path

SECRET_LABEL = "[REDACTED_SECRET]"

# Секретный сегмент ключа: точное слово или сегмент составного имени по _/-.
# «secretary» не матчится: сегмент только целым словом.
_SECRET_SEGMENT = (
    r"password|passwd|pass|pwd|passphrase|token|secret|api[_-]?key|key|"
    r"auth(?:orization)?|credentials?|session|sess(?:ion)?[_-]?id|phpsessid|"
    r"cookie|jwt|bearer|csrf|xsrf|signature"
)

# Ключ: точное имя, составное с любым числом сегментов-префиксов
# (X-Amz-Signature, AWS_SECRET_ACCESS_KEY_ID), либо секретный префикс (token_id).
_SECRET_KEY = (
    r"(?:"
    rf"(?:{_SECRET_SEGMENT})|"
    rf"(?:[A-Za-z0-9]+[_-])+(?:{_SECRET_SEGMENT})(?:[_-][A-Za-z0-9_.-]+)?|"
    rf"(?:{_SECRET_SEGMENT})[_-][A-Za-z0-9_.-]+"
    r")"
)

# Значение: кавычки или всё до конца строки/запятой/точки с запятой.
# EOL-маскирование намеренное: комментарии и многословные значения тоже скрываем.
_VALUE = r"(?:\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'|[^\r\n,;]+)"

# KEY=value / KEY: value (dotenv, YAML scalar, shell)
_SECRET_KV = re.compile(rf"(?i)\b({_SECRET_KEY})(\s*[:=]\s*)({_VALUE})")

# JSON / JS-литерал: "key":"…" / 'key': '…' (парные кавычки через \1)
_SECRET_JSON = re.compile(
    rf"(?i)([\"'])({_SECRET_KEY})(\1\s*:\s*)"
    r"(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,}}\]]+)"
)

# Windows setx NAME value
_SETX = re.compile(rf"(?i)\b(setx\s+)({_SECRET_KEY})(\s+)({_VALUE})")

# HTTP-заголовки: значение маскируется целиком до конца строки
# (Digest/NTLM/любые схемы и многотокенные значения).
_AUTH_HEADER = re.compile(r"(?i)\b((?:proxy[_-]?)?authorization\s*:\s*)[^\r\n]+")
_COOKIE_HEADER = re.compile(r"(?i)\b((?:set-cookie|cookie)\s*:\s*)[^\r\n]+")

# PEM-блоки приватных ключей: до END-маркера или до конца текста
# (хвост лога может обрезать END).
_PEM_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----"
    r".*?(?:-----END [A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----|$)",
    re.DOTALL,
)

# export/set уже покрываются _SECRET_KV на KEY=value; дополнительно:
# setx выше; shell `export KEY=value` — через KV.

_BEARER = re.compile(r"(?i)\b(Bearer\s+)\S+")
_BASIC = re.compile(r"(?i)\b(Basic\s+)\S+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")

# Высокоуверенные префиксы токенов (низкий FP)
_TOKEN_PREFIX = re.compile(
    r"\b("
    r"sk_live_[A-Za-z0-9]+|"
    r"sk_test_[A-Za-z0-9]+|"
    r"rk_live_[A-Za-z0-9]+|"
    r"pk_live_[A-Za-z0-9]+|"
    r"sk-ant-[A-Za-z0-9_-]{10,}|"
    r"sk-proj-[A-Za-z0-9_-]{10,}|"
    r"sk-or-[A-Za-z0-9_-]{10,}|"
    r"sk-svcacct-[A-Za-z0-9_-]{10,}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{10,}|"
    r"github_pat_[A-Za-z0-9_]+|"
    r"glpat-[A-Za-z0-9_-]{15,}|"
    r"xox[baprs]-[A-Za-z0-9-]+|"
    r"xapp-[A-Za-z0-9-]+|"
    r"AKIA[0-9A-Z]{16}|"
    r"ASIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z_-]{35}|"
    r"ya29\.[0-9A-Za-z_-]{10,}|"
    r"npm_[0-9A-Za-z]{30,}|"
    r"pypi-[A-Za-z0-9_-]{20,}|"
    r"dop_v1_[0-9a-f]{64}|"
    r"dapi[0-9a-f]{32}|"
    r"hf_[A-Za-z0-9]{30,}|"
    r"sbp_[0-9a-f]{40}|"
    r"shp(?:at|ca|pa)_[0-9a-f]{32}|"
    r"sq0[a-z]{3}-[A-Za-z0-9_-]{20,}|"
    r"SG\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
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

        # Заголовки и PEM-блоки — до KV, чтобы значения уходили целиком
        result = _AUTH_HEADER.sub(rf"\1{SECRET_LABEL}", result)
        result = _COOKIE_HEADER.sub(rf"\1{SECRET_LABEL}", result)
        result = _PEM_BLOCK.sub(SECRET_LABEL, result)

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


_DOTENV_LINE = re.compile(
    r"(?m)^([ \t]*#[ \t]*|[ \t]*)(export[ \t]+)?([A-Za-z_][A-Za-z0-9_.-]*[ \t]*=[ \t]*)"
    r"([^\r\n]*)$"
)


def mask_dotenv_text(text: str) -> str:
    """Маскировать значения всех строк KEY=value (для файлов вида .env*).

    В отличие от RedactionEngine, имя ключа не проверяется: в dotenv-файле
    секретным считается значение любого ключа, включая закомментированные строки.
    """
    if not text:
        return text

    def _sub(match: re.Match[str]) -> str:
        prefix = f"{match.group(1)}{match.group(2) or ''}{match.group(3)}"
        if not match.group(4).strip():
            return match.group(0)
        return f"{prefix}{SECRET_LABEL}"

    return _DOTENV_LINE.sub(_sub, text)


def sanitize_text(text: str, engine: RedactionEngine | None = None) -> str:
    """Общая граница санитарной обработки перед сериализацией."""
    if not text:
        return text
    cleaned = strip_ansi(text)
    cleaned = neutralize_controls(cleaned)
    if engine is None:
        engine = RedactionEngine()
    return engine.redact(cleaned)
