"""Read-only Supabase data catalog used by the Team Pack workspace.

The browser never receives database credentials and cannot supply arbitrary SQL.
Only the 26 business tables declared below can be listed or read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg2 import sql

from app.database.repository import query_db


CATALOG_TABLES: tuple[dict[str, str], ...] = (
    {
        "name": "dataset_guide",
        "label": "01_DATASET_GUIDE",
        "description": "Hướng dẫn dữ liệu",
    },
    {"name": "company", "label": "02_OPC_PROFILE", "description": "Hồ sơ doanh nghiệp"},
    {"name": "customer", "label": "03_CUSTOMERS", "description": "Khách hàng"},
    {"name": "contract", "label": "04_CONTRACTS", "description": "Hợp đồng"},
    {"name": "service", "label": "05_PRODUCTS", "description": "Sản phẩm và dịch vụ"},
    {"name": "orders", "label": "06_ORDERS", "description": "Đơn hàng"},
    {"name": "invoice", "label": "07_INVOICES", "description": "Hóa đơn"},
    {"name": "bank_txn", "label": "08_BANK_TXN", "description": "Giao dịch ngân hàng"},
    {"name": "cashflow", "label": "09_CASHFLOW", "description": "Dòng tiền"},
    {"name": "credit_profile", "label": "10_CREDIT_PROFILE", "description": "Hồ sơ tín dụng"},
    {"name": "bank_product", "label": "11_BANK_PRODUCTS", "description": "Sản phẩm ngân hàng"},
    {"name": "decision", "label": "12_DECISIONS", "description": "Quyết định"},
    {"name": "risk_rule", "label": "13_RISK_RULES", "description": "Quy tắc rủi ro"},
    {"name": "alert", "label": "14_ALERTS", "description": "Cảnh báo"},
    {"name": "data_class", "label": "15_DATA_CLASS", "description": "Phân loại dữ liệu"},
    {"name": "masking_example", "label": "16_MASKING_EXAMPLES", "description": "Mẫu che dữ liệu"},
    {"name": "data_dictionary", "label": "17_DATA_DICTIONARY", "description": "Từ điển dữ liệu"},
    {"name": "agent_task", "label": "18_AGENT_TASKS", "description": "Nhiệm vụ agent"},
    {"name": "api_catalog", "label": "19_API_CATALOG", "description": "Danh mục API"},
    {
        "name": "api_assumption",
        "label": "20_API_ASSUMPTIONS",
        "description": "Giả định API",
    },
    {
        "name": "api_handling_rule",
        "label": "21_API_HANDLING_RULES",
        "description": "Quy tắc xử lý API",
    },
    {
        "name": "ai_use_disclosure",
        "label": "22_AI_USE_DISCLOSURES",
        "description": "Công bố sử dụng AI",
    },
    {
        "name": "crisis_card_template",
        "label": "23_CRISIS_CARD_TEMPLATE",
        "description": "Mẫu tình huống",
    },
    {"name": "design_log", "label": "24_DESIGN_LOG", "description": "Nhật ký thiết kế"},
    {"name": "public_test", "label": "25_PUBLIC_TESTS", "description": "Kiểm thử công khai"},
    {
        "name": "runtime_log_schema",
        "label": "26_RUNTIME_LOG_SCHEMA",
        "description": "Schema runtime log",
    },
)

_TABLE_BY_NAME = {table["name"]: table for table in CATALOG_TABLES}


def _available_table_names() -> set[str]:
    rows = query_db(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type IN ('BASE TABLE', 'VIEW')
        """
    )
    return {
        str(row["table_name"])
        for row in rows or []
        if row.get("table_name")
    }


def list_catalog_tables() -> dict[str, Any]:
    """Return the ordered business catalog, filtered to tables that exist."""
    available = _available_table_names()
    tables = [dict(table) for table in CATALOG_TABLES if table["name"] in available]
    return {"tables": tables, "count": len(tables)}


def _require_catalog_table(table_name: str) -> dict[str, str]:
    table = _TABLE_BY_NAME.get(table_name)
    if table is None:
        raise KeyError(f"Table is not available in the data catalog: {table_name}")
    if table_name not in _available_table_names():
        raise LookupError(f"Supabase table does not exist: {table_name}")
    return table


def read_catalog_table(table_name: str) -> dict[str, Any]:
    """Read every row from one allowlisted public table."""
    table = _require_catalog_table(table_name)
    statement = sql.SQL("SELECT * FROM public.{}").format(sql.Identifier(table_name))
    rows = query_db(statement) or []

    if rows:
        columns = list(rows[0])
    else:
        column_rows = query_db(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        columns = [str(row["column_name"]) for row in column_rows or []]

    return {
        "table": dict(table),
        "columns": columns,
        "rows": rows,
        "count": len(rows),
        "loaded_at": datetime.now(UTC).isoformat(),
    }


def list_contract_options() -> dict[str, Any]:
    """Return compact contract labels for the workspace selector."""
    _require_catalog_table("contract")
    rows = query_db("SELECT * FROM public.contract ORDER BY contract_id") or []
    customer_rows = query_db("SELECT * FROM public.customer") or []
    customers = {
        str(row["customer_id"]): row
        for row in customer_rows
        if row.get("customer_id")
    }
    contracts = [
        {
            "contract_id": str(row["contract_id"]),
            "customer_id": row.get("customer_id"),
            "customer_name": _customer_display_name(
                customers.get(str(row.get("customer_id")), {})
            ),
            "description": row.get("description"),
        }
        for row in rows
        if row.get("contract_id")
    ]
    return {"contracts": contracts, "count": len(contracts)}


def _customer_display_name(customer: dict[str, Any]) -> str | None:
    for field in ("customer_name", "company_name", "legal_name", "name"):
        value = customer.get(field)
        if value:
            return str(value)
    return None


__all__ = [
    "CATALOG_TABLES",
    "list_catalog_tables",
    "list_contract_options",
    "read_catalog_table",
]
