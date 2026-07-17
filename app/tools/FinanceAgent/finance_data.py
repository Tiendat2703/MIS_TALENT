"""Lớp truy cập dữ liệu cho Finance Agent.

Mặc định dùng mock (Team Pack) để chạy được end-to-end khi CHƯA có DB. Khi
Supabase sẵn sàng: đặt FINANCE_USE_MOCK=false và kiểm tra lại TABLES cho khớp
tên bảng thật. Mỗi hàm trả về list[dict] (giống RealDictCursor của query_db),
riêng get_profile trả về dict field->value.
"""

from __future__ import annotations

import os

from app.tools.FinanceAgent import mock_data


def _use_mock() -> bool:
    return os.getenv("FINANCE_USE_MOCK", "true").strip().lower() != "false"


# Tên bảng DB — CẦN xác nhận lại với schema Supabase thật khi tắt mock.
# ("order" là từ khóa SQL nên phải để trong ngoặc kép khi query.)
TABLES = {
    "contracts": "contract",
    "orders": '"order"',
    "invoices": "invoice",
    "bank_txn": "bank_txn",
    "cashflow": "cashflow",
    "customers": "customer",
    "services": "service",
    "profile": "company",
}


def _fetch(table_key: str, mock_rows: list[dict]) -> list[dict]:
    if _use_mock():
        return mock_rows
    from app.database.repository import query_db  # import trễ để mock không cần psycopg2

    rows = query_db(f"SELECT * FROM {TABLES[table_key]}")
    if not isinstance(rows, list):
        raise RuntimeError(f"Query {table_key} không trả về list")
    return rows


def get_contracts() -> list[dict]:
    return _fetch("contracts", mock_data.CONTRACTS)


def get_orders() -> list[dict]:
    return _fetch("orders", mock_data.ORDERS)


def get_invoices() -> list[dict]:
    return _fetch("invoices", mock_data.INVOICES)


def get_bank_txn() -> list[dict]:
    return _fetch("bank_txn", mock_data.BANK_TXN)


def get_cashflow() -> list[dict]:
    return _fetch("cashflow", mock_data.CASHFLOW)


def get_customers() -> list[dict]:
    return _fetch("customers", mock_data.CUSTOMERS)


def get_services() -> list[dict]:
    return _fetch("services", mock_data.SERVICES)


def get_profile() -> dict:
    """02_OPC_PROFILE ở dạng field/value. Mock trả thẳng dict; DB thì pivot lại."""
    if _use_mock():
        return dict(mock_data.PROFILE)
    from app.database.repository import query_db

    rows = query_db(f"SELECT * FROM {TABLES['profile']}")
    if rows and "field" in rows[0] and "value" in rows[0]:
        return {r["field"]: r["value"] for r in rows}
    return rows[0] if rows else {}


def load_all() -> dict:
    """Nạp toàn bộ dữ liệu Finance Agent cần trong một lần (bước 1)."""
    return {
        "contracts": get_contracts(),
        "orders": get_orders(),
        "invoices": get_invoices(),
        "bank_txn": get_bank_txn(),
        "cashflow": get_cashflow(),
        "customers": get_customers(),
        "services": get_services(),
        "profile": get_profile(),
        "source": "mock" if _use_mock() else "database",
    }
