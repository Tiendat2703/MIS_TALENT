"""Deterministic masking for Risk Pack alerts."""

from __future__ import annotations

import hashlib
import re

from app.schema.handoff_packs import RiskAlert

_IDENTIFIER = re.compile(r"\b(?:TXN|CON|CR|ORD|CUS|ACC|OPC)[-_][A-Z0-9]+\b", re.I)


def tokenize_identifier(value: str) -> str:
    prefix = value.split("-", 1)[0].split("_", 1)[0].upper()
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8].upper()
    return f"TOK-{prefix}-{digest}"


def mask_text_identifiers(value: str | None) -> str | None:
    if value is None:
        return None
    return _IDENTIFIER.sub(lambda match: tokenize_identifier(match.group(0)), value)


def mask_alert(alert: RiskAlert) -> RiskAlert:
    safe = alert.model_copy(deep=True)
    safe.related_record = mask_text_identifiers(safe.related_record)
    return safe
