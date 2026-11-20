"""JSON-рендерер отчёта."""

from __future__ import annotations

import json
from typing import Any

from devreport.models import Report
from devreport.redaction.engine import RedactionEngine, sanitize_text


def render_json(report: Report, engine: RedactionEngine | None = None) -> str:
    if engine is None:
        engine = RedactionEngine()
    data = report.to_dict()
    sanitized = _sanitize_tree(data, engine)
    return json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sanitize_tree(value: Any, engine: RedactionEngine) -> Any:
    if isinstance(value, str):
        return sanitize_text(value, engine)
    if isinstance(value, list):
        return [_sanitize_tree(v, engine) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_tree(v, engine) for k, v in value.items()}
    return value
