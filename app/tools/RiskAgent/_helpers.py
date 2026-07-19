"""Shared validation helpers for Risk Agent DB tools."""

from __future__ import annotations

from typing import Any, TypeVar

from app.schema.handoff_packs import Severity

T = TypeVar("T")


def require_rows(value: Any, table_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise RuntimeError(f"Expected {table_name} query to return a list of rows")
    return value


def parse_severity(value: Any) -> Severity:
    return Severity(str(value).strip().upper())
