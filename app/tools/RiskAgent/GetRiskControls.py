"""Read risk rules, alerts, and data-protection controls from PostgreSQL."""

from __future__ import annotations

import json

from agents import function_tool

from app.database.repository import query_db
from app.schema.risk_db_models import (
    BankTransaction,
    DataClassRule,
    MaskingExample,
    OrderRecord,
    RiskRule,
)
from app.schema.handoff_packs import FinanceFeaturePack, RiskAlert
from app.tools.RiskAgent._helpers import parse_severity, require_rows
from app.tools.RiskAgent._masking import mask_alert, mask_example


# Compatibility export only. Rule activity must come from governed rule-master
# data, not a hard-coded application blacklist. The current table has no
# ``active`` column, so all seven rows are evaluated for applicability.
DISABLED_RISK_RULE_IDS: frozenset[str] = frozenset()


def get_risk_rules_impl() -> list[RiskRule]:
    rows = query_db(
        """
        SELECT *
        FROM risk_rule
        ORDER BY rule_id
        """
    )
    return [
        RiskRule(
            rule_id=row["rule_id"],
            risk_type=row["risk_type"],
            trigger_condition=row["trigger_condition"],
            severity=parse_severity(row["severity"]),
            required_action=row["required_action"],
            owner_agent=row["owner_agent"],
            confidence_score=row.get("confidence_score"),
        )
        for row in require_rows(rows, "risk_rule")
    ]


def get_contract_bank_transactions_impl(
    finance_pack: FinanceFeaturePack,
) -> list[BankTransaction]:
    """Read only bank transactions traceable to this contract handoff.

    Transactions are linked by an explicit source id or by an invoice id in the
    transaction description. Unrelated high-risk transactions must never leak
    into a contract assessment.
    """
    rows = query_db(
        """
        SELECT txn_id, txn_date, bank, account_id, direction, description,
               amount, counterparty_id, txn_status, transaction_risk_score
        FROM bank_txn
        ORDER BY txn_date, txn_id
        """
    ) or []
    source_ids = {str(item) for item in finance_pack.source_record_ids}
    invoice_ids = {item for item in source_ids if item.upper().startswith("INV-")}
    matched: list[BankTransaction] = []
    for row in rows:
        txn_id = str(row.get("txn_id") or "")
        description = str(row.get("description") or "").casefold()
        linked_by_invoice = any(
            invoice_id.casefold() in description for invoice_id in invoice_ids
        )
        if txn_id in source_ids or linked_by_invoice:
            matched.append(BankTransaction(**row))
    return matched


def get_portfolio_bank_transactions_impl() -> list[BankTransaction]:
    """Read portfolio transactions without attributing them to a contract."""
    rows = query_db(
        """
        SELECT txn_id, txn_date, bank, account_id, direction, description,
               amount, counterparty_id, txn_status, transaction_risk_score
        FROM bank_txn
        ORDER BY txn_date, txn_id
        """
    ) or []
    return [BankTransaction(**row) for row in rows]


def get_contract_orders_impl(contract_id: str) -> list[OrderRecord]:
    """Read the authoritative order/progress rows for one contract."""
    rows = query_db(
        """
        SELECT order_id, contract_id, customer_id, order_date, due_date, status,
               service_id, order_revenue, estimated_cost, delivery_note
        FROM orders
        WHERE contract_id = %s
        ORDER BY order_id
        """,
        (contract_id,),
    ) or []
    return [OrderRecord(**row) for row in rows]


def load_risk_source_evidence_impl(
    finance_pack: FinanceFeaturePack,
) -> dict[str, list[BankTransaction] | list[OrderRecord]]:
    """Load contract and portfolio evidence with explicit scope boundaries."""
    return {
        "bank_transactions": get_contract_bank_transactions_impl(finance_pack),
        "portfolio_bank_transactions": get_portfolio_bank_transactions_impl(),
        "orders": get_contract_orders_impl(finance_pack.contract_id),
    }


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
    """Read all organizer-provided RR rules from the governed rule master."""
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
