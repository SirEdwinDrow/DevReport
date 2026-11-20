"""Типизированные модели отчёта DevReport."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum, StrEnum
from typing import Any


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class ToolStatus(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SystemInfo:
    os_family: str
    os_release: str
    architecture: str
    python_version: str


@dataclass(frozen=True)
class ToolInfo:
    name: str
    status: ToolStatus
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ProjectFileInfo:
    name: str
    present: bool


@dataclass(frozen=True)
class EnvComparison:
    status: CheckStatus
    missing_keys: tuple[str, ...] = ()
    extra_keys: tuple[str, ...] = ()
    duplicate_keys: tuple[str, ...] = ()
    unparsed_lines: tuple[int, ...] = ()
    detail: str | None = None


@dataclass(frozen=True)
class PortCheckResult:
    status: CheckStatus
    port: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class LogStats:
    requested: bool
    path: str | None = None
    lines_returned: int = 0
    bytes_read: int = 0
    truncated_by_size: bool = False
    truncated_by_line_length: bool = False
    decoding_replacements: bool = False
    rejected_reason: str | None = None


@dataclass(frozen=True)
class CheckResult:
    code: str
    status: CheckStatus
    title: str
    description: str
    recommendation: str | None = None


@dataclass
class Report:
    schema_version: str
    tool_version: str
    created_at_utc: str
    system: SystemInfo
    tools: list[ToolInfo] = field(default_factory=list)
    project_files: list[ProjectFileInfo] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    env_comparison: EnvComparison | None = None
    port_check: PortCheckResult | None = None
    log_stats: LogStats | None = None
    log_excerpt: str | None = None
    limitations: list[str] = field(default_factory=list)
    privacy_warning: str = (
        "Автоматическое маскирование неполное: оно не удаляет все секреты "
        "(нестандартные имена ключей, свободный текст без key=value, неизвестные форматы). "
        "Обязательно проверьте отчёт вручную перед публикацией."
    )

    def to_dict(self) -> dict[str, Any]:
        """Предсказуемый словарь для JSON-сериализации."""
        data = asdict(self)
        # Enum → value
        for tool in data.get("tools", []):
            if isinstance(tool.get("status"), Enum):
                tool["status"] = tool["status"].value
            elif hasattr(tool.get("status"), "value"):
                tool["status"] = tool["status"]
        for check in data.get("checks", []):
            status = check.get("status")
            if isinstance(status, Enum):
                check["status"] = status.value
        env = data.get("env_comparison")
        if env and isinstance(env.get("status"), Enum):
            env["status"] = env["status"].value
        port = data.get("port_check")
        if port and isinstance(port.get("status"), Enum):
            port["status"] = port["status"].value
        # Сортируем списки, где порядок не несёт смысла
        data["tools"] = sorted(data["tools"], key=lambda t: t["name"])
        data["project_files"] = sorted(data["project_files"], key=lambda f: f["name"])
        data["checks"] = sorted(data["checks"], key=lambda c: c["code"])
        data["limitations"] = sorted(data["limitations"])
        return data
