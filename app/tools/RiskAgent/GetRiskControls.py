"""Read risk rules, alerts, and data-protection controls from PostgreSQL."""

from __future__ import annotations

import json

from agents import function_tool

from app.database.repository import query_db
from app.schema.risk_db_models import (
    DataClassRule,
    MaskingExample,
    RiskRule,
)
from app.schema.handoff_packs import RiskAlert
from app.tools.RiskAgent._helpers import parse_severity, require_rows
from app.tools.RiskAgent._masking import mask_alert, mask_example


# Business policy: a large requested amount by itself is not a risk rule and
# must not block or reject an otherwise eligible contract. Keep the database row
# for audit/history, but exclude it from every active runtime rule set.
DISABLED_RISK_RULE_IDS = frozenset({"RR-005"})


def get_risk_rules_impl() -> list[RiskRule]:
    rows = query_db(
        """
        SELECT rule_id, risk_type, trigger_condition, severity,
               required_action, owner_agent
        FROM risk_rule
        ORDER BY rule_id
        """
    )
    return [
        RiskRule(**{**row, "severity": parse_severity(row["severity"])})
        for row in require_rows(rows, "risk_rule")
        if str(row.get("rule_id")) not in DISABLED_RISK_RULE_IDS
    ]


def get_alerts_impl() -> list[RiskAlert]:
    rows = query_db(
        """
        SELECT alert_id, alert_date, alert_type, related_record, severity,
               risk_score, description, recommended_action
        FROM alert
        ORDER BY alert_date, alert_id
        """
    )
    return [
        RiskAlert(
            **{
                **row,
                "severity": parse_severity(row["severity"])
                if row.get("severity")
                else None,
            }
        )
        for row in require_rows(rows, "alert")
    ]


def get_data_classes_impl() -> list[DataClassRule]:
    rows = query_db(
        """
        SELECT data_pattern, example_field, classification, external_api_rule,
               masking_or_tokenization, logging_rule
        FROM data_class
        ORDER BY data_pattern
        """
    )
    return [DataClassRule(**row) for row in require_rows(rows, "data_class")]


def get_masking_examples_impl() -> list[MaskingExample]:
    rows = query_db(
        """
        SELECT source_field, raw_example, masked_example, tokenized_example,
               allowed_for_partner_api, reason
        FROM masking_example
        ORDER BY source_field
        """
    )
    return [
        MaskingExample(**row)
        for row in require_rows(rows, "masking_example")
    ]


@function_tool
def get_risk_rules() -> list[RiskRule]:
    """Read all active organizer-provided RR rules from PostgreSQL."""
    return get_risk_rules_impl()


@function_tool
def get_alerts() -> list[RiskAlert]:
    """Read organizer-provided alerts with related identifiers masked."""
    return [mask_alert(item) for item in get_alerts_impl()]


@function_tool
def get_data_classes() -> list[DataClassRule]:
    """Read organizer-provided data classification and handling rules."""
    return get_data_classes_impl()


@function_tool
def get_masking_examples() -> list[MaskingExample]:
    """Read masking examples without exposing their raw example values."""
    return [mask_example(item) for item in get_masking_examples_impl()]


if __name__ == "__main__":
    output = {
        "risk_rules": [item.model_dump(mode="json") for item in get_risk_rules_impl()],
        "alerts": [item.model_dump(mode="json") for item in get_alerts_impl()],
        "data_classes": [
            item.model_dump(mode="json") for item in get_data_classes_impl()
        ],
        "masking_examples": [
            item.model_dump(mode="json") for item in get_masking_examples_impl()
        ],
    }
    print(json.dumps(output, default=str, ensure_ascii=False, indent=2))
