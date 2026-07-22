"""Deterministic completeness rules for one selected database contract."""

from __future__ import annotations

from datetime import date, datetime
from numbers import Number
from typing import Any, Literal, Mapping, Sequence

from app.schema.financeAgent import FinanceCompletenessIssue


DataType = Literal["text", "number", "date", "boolean"]


# ``data_key`` matches ``finance_data.load_all`` while ``table`` matches the
# public Supabase table and the Team Pack route.
CONTRACT_SCOPE_TABLES: tuple[dict[str, Any], ...] = (
    {
        "data_key": "contracts",
        "table": "contract",
        "table_label": "04_CONTRACTS",
        "primary_key": "contract_id",
        "columns": {
            "contract_id": "text",
            "customer_id": "text",
            "start_date": "date",
            "end_date": "date",
            "status": "text",
            "description": "text",
            "contract_value": "number",
            "gross_margin": "number",
            "payment_terms": "text",
        },
    },
    {
        "data_key": "orders",
        "table": "orders",
        "table_label": "06_ORDERS",
        "primary_key": "order_id",
        "columns": {
            "order_id": "text",
            "contract_id": "text",
            "customer_id": "text",
            "order_date": "date",
            "due_date": "date",
            "status": "text",
            "service_id": "text",
            "order_revenue": "number",
            "estimated_cost": "number",
            "delivery_note": "text",
        },
    },
    {
        "data_key": "invoices",
        "table": "invoice",
        "table_label": "07_INVOICES",
        "primary_key": "invoice_id",
        "columns": {
            "invoice_id": "text",
            "order_id": "text",
            "customer_id": "text",
            "issue_date": "date",
            "due_date": "date",
            "status": "text",
            "invoice_amount": "number",
            "paid_date": "date",
        },
    },
)


def is_missing_value(value: object) -> bool:
    """Return true only for null or whitespace-only text.

    Numeric zero and ``False`` are intentionally valid.
    """
    return value is None or (isinstance(value, str) and not value.strip())


def _infer_data_type(values: Sequence[object]) -> DataType:
    for value in values:
        if is_missing_value(value):
            continue
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (date, datetime)):
            return "date"
        if isinstance(value, Number):
            return "number"
        return "text"
    return "text"


def _columns_for_rows(
    configured: Mapping[str, DataType],
    rows: Sequence[Mapping[str, object]],
) -> list[tuple[str, DataType]]:
    """Keep schema order and include any additional columns returned by DB."""
    result = list(configured.items())
    configured_names = set(configured)
    extra_names: list[str] = []
    for row in rows:
        for column in row:
            if column not in configured_names and column not in extra_names:
                extra_names.append(column)
    for column in sorted(extra_names):
        result.append(
            (column, _infer_data_type([row.get(column) for row in rows]))
        )
    return result


def _record_id(
    row: Mapping[str, object],
    primary_key: str,
    row_index: int,
) -> str:
    value = row.get(primary_key)
    if not is_missing_value(value):
        return str(value)
    return f"row-{row_index + 1}"


def _is_allowed_missing(
    table: str,
    column: str,
    row: Mapping[str, object],
) -> bool:
    if table != "invoice" or column != "paid_date":
        return False
    return str(row.get("status") or "").strip().casefold() != "paid"


def scope_data_to_contract(
    data: Mapping[str, object],
    contract_id: str,
) -> dict[str, list[Mapping[str, object]]]:
    """Select only rows that have a deterministic relationship to a contract."""
    normalized_id = contract_id.strip()
    contracts = [
        row
        for row in (data.get("contracts") or [])
        if isinstance(row, Mapping)
        and str(row.get("contract_id") or "").strip() == normalized_id
    ]
    if not contracts:
        raise LookupError(f"Contract does not exist: {normalized_id}")
    if len(contracts) > 1:
        raise ValueError(f"Duplicate contract_id in database: {normalized_id}")

    orders = [
        row
        for row in (data.get("orders") or [])
        if isinstance(row, Mapping)
        and str(row.get("contract_id") or "").strip() == normalized_id
    ]
    order_ids = {
        str(row.get("order_id"))
        for row in orders
        if not is_missing_value(row.get("order_id"))
    }
    invoices = [
        row
        for row in (data.get("invoices") or [])
        if isinstance(row, Mapping)
        and str(row.get("order_id") or "") in order_ids
    ]
    return {
        "contracts": contracts,
        "orders": orders,
        "invoices": invoices,
    }


def check_selected_contract_completeness(
    data: Mapping[str, object],
    contract_id: str,
) -> list[FinanceCompletenessIssue]:
    """Find missing cells only in the selected contract and its linked rows."""
    scoped_data = scope_data_to_contract(data, contract_id)
    issues: list[FinanceCompletenessIssue] = []
    for rule in CONTRACT_SCOPE_TABLES:
        raw_rows = scoped_data.get(rule["data_key"])
        rows = raw_rows if isinstance(raw_rows, list) else []
        typed_rows = [row for row in rows if isinstance(row, Mapping)]
        columns = _columns_for_rows(rule["columns"], typed_rows)

        for row_index, row in enumerate(typed_rows):
            record_id = _record_id(row, rule["primary_key"], row_index)
            for column, data_type in columns:
                if not is_missing_value(row.get(column)):
                    continue
                if _is_allowed_missing(rule["table"], column, row):
                    continue
                issues.append(
                    FinanceCompletenessIssue(
                        issue_id=f"{rule['table']}|{record_id}|{column}",
                        table=rule["table"],
                        table_label=rule["table_label"],
                        record_id=record_id,
                        column=column,
                        data_type=data_type,
                        reason=f"Thiếu {column} của {record_id}",
                    )
                )
    return issues


__all__ = [
    "CONTRACT_SCOPE_TABLES",
    "check_selected_contract_completeness",
    "is_missing_value",
    "scope_data_to_contract",
]
