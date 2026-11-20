"""Сравнение ключей .env и .env.example без чтения значений в отчёт."""

from __future__ import annotations

from pathlib import Path

from devreport.models import CheckStatus, EnvComparison
from devreport.utils.paths import is_symlink

MAX_ENV_FILE_BYTES = 256 * 1024


class EnvParseResult:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.duplicates: list[str] = []
        self.unparsed_lines: list[int] = []
        self.error: str | None = None


def parse_env_keys(text: str) -> EnvParseResult:
    """Простой parser: KEY=value, export KEY=value, KEY=, # comment.

    Multiline и сложный синтаксис dotenv не поддерживаются полностью.
    """
    result = EnvParseResult()
    seen: set[str] = set()
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        working = line
        if working.startswith("export "):
            working = working[7:].lstrip()
        if "=" not in working:
            result.unparsed_lines.append(lineno)
            continue
        key, _sep, _value = working.partition("=")
        key = key.strip()
        if not key or not _is_simple_key(key):
            result.unparsed_lines.append(lineno)
            continue
        if key in seen:
            if key not in result.duplicates:
                result.duplicates.append(key)
        else:
            seen.add(key)
            result.keys.append(key)
    return result


def _is_simple_key(key: str) -> bool:
    if not key:
        return False
    # Простой идентификатор dotenv
    first = key[0]
    if not (first.isalpha() or first == "_"):
        return False
    return all(c.isalnum() or c == "_" for c in key)


def _read_env_file(path: Path) -> tuple[str | None, str | None]:
    """Вернуть (text, error). Не следует symlink."""
    try:
        if is_symlink(path):
            return None, "symlink отклонён"
        if not path.is_file():
            return None, "не обычный файл"
        size = path.stat().st_size
        if size > MAX_ENV_FILE_BYTES:
            return None, f"файл превышает лимит {MAX_ENV_FILE_BYTES} байт"
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        return text, None
    except OSError as exc:
        return None, f"недоступен: {exc.__class__.__name__}"


def compare_env_files(project_root: Path) -> EnvComparison:
    example_path = project_root / ".env.example"
    env_path = project_root / ".env"

    example_exists = False
    env_exists = False
    try:
        example_exists = example_path.exists() and not example_path.is_dir()
    except OSError:
        return EnvComparison(
            status=CheckStatus.UNKNOWN,
            detail="не удалось проверить .env.example",
        )
    try:
        env_exists = env_path.exists() and not env_path.is_dir()
    except OSError:
        env_exists = False

    if not example_exists:
        return EnvComparison(
            status=CheckStatus.SKIPPED,
            detail=".env.example отсутствует — сравнение пропущено",
        )

    example_text, example_err = _read_env_file(example_path)
    if example_err or example_text is None:
        return EnvComparison(
            status=CheckStatus.UNKNOWN,
            detail=f".env.example: {example_err}",
        )

    example_parsed = parse_env_keys(example_text)

    if not env_exists:
        return EnvComparison(
            status=CheckStatus.WARNING,
            missing_keys=tuple(sorted(example_parsed.keys)),
            unparsed_lines=tuple(example_parsed.unparsed_lines),
            detail=".env отсутствует при наличии .env.example",
        )

    env_text, env_err = _read_env_file(env_path)
    if env_err or env_text is None:
        return EnvComparison(
            status=CheckStatus.UNKNOWN,
            detail=f".env: {env_err}",
        )

    env_parsed = parse_env_keys(env_text)
    example_set = set(example_parsed.keys)
    env_set = set(env_parsed.keys)
    missing = tuple(sorted(example_set - env_set))
    extra = tuple(sorted(env_set - example_set))
    duplicates = tuple(sorted(set(example_parsed.duplicates) | set(env_parsed.duplicates)))
    unparsed = tuple(sorted(set(example_parsed.unparsed_lines) | set(env_parsed.unparsed_lines)))

    status = CheckStatus.WARNING if missing or duplicates else CheckStatus.OK

    return EnvComparison(
        status=status,
        missing_keys=missing,
        extra_keys=extra,
        duplicate_keys=duplicates,
        unparsed_lines=unparsed,
        detail=None,
    )
