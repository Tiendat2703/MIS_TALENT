"""Lớp truy cập dữ liệu thật từ Supabase cho Finance Agent.

Không có mock hoặc fallback dữ liệu. Lỗi kết nối, sai schema hay bảng trống được
trả về đúng trạng thái để pipeline dừng hoặc yêu cầu bổ sung dữ liệu.
"""

from __future__ import annotations

import os

from app.database.repository import query_db


# Khóa chính dùng khi áp dữ liệu thật do người dùng bổ sung qua form.
PRIMARY_KEYS = {
    "contracts": "contract_id",
    "orders": "order_id",
    "invoices": "invoice_id",
    "bank_txn": "txn_id",
    "cashflow": "month",
    "customers": "customer_id",
    "services": "service_id",
}


# Tên bảng DB (đã đối chiếu với schema Supabase thật).
TABLES = {
    "contracts": "contract",
    "orders": "orders",
    "invoices": "invoice",
    "bank_txn": "bank_txn",
    "cashflow": "cashflow",
    "customers": "customer",
    "services": "service",
    "profile": "company",
}


def _fetch(table_key: str) -> list[dict]:
    rows = query_db(f"SELECT * FROM {TABLES[table_key]}")
    if not isinstance(rows, list):
        raise RuntimeError(f"Query {table_key} không trả về list")
    return rows


def get_contracts() -> list[dict]:
    return _fetch("contracts")


def get_orders() -> list[dict]:
    return _fetch("orders")


def get_invoices() -> list[dict]:
    return _fetch("invoices")


def get_bank_txn() -> list[dict]:
    return _fetch("bank_txn")


def get_cashflow() -> list[dict]:
    return _fetch("cashflow")


def get_customers() -> list[dict]:
    return _fetch("customers")


def get_services() -> list[dict]:
    return _fetch("services")


def get_profile() -> dict:
    """02_OPC_PROFILE ở dạng field/value; pivot dữ liệu DB khi cần."""
    rows = query_db(f"SELECT * FROM {TABLES['profile']}")
    if rows and "field" in rows[0] and "value" in rows[0]:
        return {r["field"]: r["value"] for r in rows}
    return rows[0] if rows else {}


def load_all() -> dict:
    """Nạp toàn bộ dữ liệu Finance Agent cần từ database thật."""
    if os.getenv("FINANCE_SCENARIO"):
        raise RuntimeError(
            "FINANCE_SCENARIO is disabled: production pipeline does not allow "
            "simulated data overrides"
        )

    return {
        "contracts": get_contracts(),
        "orders": get_orders(),
        "invoices": get_invoices(),
        "bank_txn": get_bank_txn(),
        "cashflow": get_cashflow(),
        "customers": get_customers(),
        "services": get_services(),
        "profile": get_profile(),
        "source": "database",
        "scenario": None,
    }
