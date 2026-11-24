"""Точка входа: python -m devreport."""

from __future__ import annotations

from devreport.cli import app, ensure_utf8_stdio


def main() -> None:
    ensure_utf8_stdio()
    app()


if __name__ == "__main__":
    main()
