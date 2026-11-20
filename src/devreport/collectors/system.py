"""Сбор системной информации."""

from __future__ import annotations

import platform
import sys

from devreport.models import SystemInfo


def collect_system_info() -> SystemInfo:
    os_family = platform.system() or "unknown"
    # Linux: platform.freedesktop_os_release при наличии
    os_release = _os_release(os_family)
    architecture = platform.machine() or "unknown"
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return SystemInfo(
        os_family=os_family,
        os_release=os_release,
        architecture=architecture,
        python_version=python_version,
    )


def _os_release(os_family: str) -> str:
    if os_family == "Linux":
        try:
            info = platform.freedesktop_os_release()
            name = info.get("PRETTY_NAME") or info.get("NAME") or ""
            version = info.get("VERSION_ID") or info.get("VERSION") or ""
            if name and version and version not in name:
                return f"{name} {version}".strip()
            if name:
                return name
        except (OSError, AttributeError, ValueError):
            pass
    # Windows / fallback
    release = platform.release() or ""
    version = platform.version() or ""
    if release and version:
        return f"{release} ({version})"
    return release or version or "unknown"
