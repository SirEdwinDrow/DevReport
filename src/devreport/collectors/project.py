"""Поиск известных файлов в корне проекта."""

from __future__ import annotations

from pathlib import Path

from devreport.models import ProjectFileInfo

KNOWN_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Dockerfile",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
    ".env",
    ".env.example",
    ".gitignore",
)


def collect_project_files(project_root: Path) -> list[ProjectFileInfo]:
    results: list[ProjectFileInfo] = []
    for name in KNOWN_FILES:
        path = project_root / name
        present = False
        try:
            # Только существование в корне, без чтения содержимого
            # is_file() False для директорий; symlink на файл считаем present
            present = path.exists() and not path.is_dir()
        except OSError:
            present = False
        results.append(ProjectFileInfo(name=name, present=present))
    return results
