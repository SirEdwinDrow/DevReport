"""Рендереры отчётов."""

from devreport.renderers.json import render_json
from devreport.renderers.markdown import render_markdown

__all__ = ["render_json", "render_markdown"]
