"""Маскирование чувствительных данных."""

from devreport.redaction.engine import RedactionEngine, sanitize_text

__all__ = ["RedactionEngine", "sanitize_text"]
