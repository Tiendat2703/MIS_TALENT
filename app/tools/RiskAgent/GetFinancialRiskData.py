"""Read company, cashflow, contract, credit, and order risk inputs."""

from __future__ import annotations

import json

from agents import function_tool

from app.database.repository import query_db
from app.schema.risk_db_models import (
    CashflowRecord,
    CompanyProfile,
    ContractRecord,
    CreditProfile,
    OrderRecord,
)
from app.tools.RiskAgent._helpers import require_rows
from app.tools.RiskAgent._masking import (
    mask_company_profile,
    mask_contract,
    mask_credit_profile,
    mask_order,
)


def get_cashflows_impl(month: str | None = None) -> list[CashflowRecord]:
    sql = """
        SELECT month, expected_cash_in, expected_cash_out, direct_cost, opex,
               cash_reserve_minimum, projected_closing_cash, management_note
        FROM cashflow
    """
    params = None
    if month is not None:
        sql += " WHERE month = %s"
        params = (month,)
    sql += " ORDER BY month"
    rows = query_db(sql, params)
    return [CashflowRecord(**row) for row in require_rows(rows, "cashflow")]


def get_company_profiles_impl(company_id: str | None = None) -> list[CompanyProfile]:
    sql = """
        SELECT company_id, company_name, business_model, founder, headquarter,
               current_regions, target_regions, core_services,
               operating_constraint, governance_rule, cash_reserve_minimum,
               target_gross_margin, late_delivery_penalty_rate
        FROM company
    """
    params = None
    if company_id is not None:
        sql += " WHERE company_id = %s"
        params = (company_id,)
    sql += " ORDER BY company_id"
    rows = query_db(sql, params)
    return [CompanyProfile(**row) for row in require_rows(rows, "company")]


def get_contracts_impl(contract_id: str | None = None) -> list[ContractRecord]:
    sql = """
        SELECT contract_id, customer_id, start_date, end_date, status,
               description, contract_value, gross_margin, payment_terms
        FROM contract
    """
    params = None
    if contract_id is not None:
        sql += " WHERE contract_id = %s"
        params = (contract_id,)
    sql += " ORDER BY contract_id"
    rows = query_db(sql, params)
    return [ContractRecord(**row) for row in require_rows(rows, "contract")]


def get_credit_profiles_impl(company_id: str | None = None) -> list[CreditProfile]:
    sql = """
        SELECT credit_case_id, company_id, request_type, requested_amount,
               tenor, collateral_or_basis, eligibility_score, precheck_note,
               approval_status
        FROM credit_profile
    """
    params = None
    if company_id is not None:
        sql += " WHERE company_id = %s"
        params = (company_id,)
    sql += " ORDER BY credit_case_id"
    rows = query_db(sql, params)
    return [CreditProfile(**row) for row in require_rows(rows, "credit_profile")]


def get_orders_impl(contract_id: str | None = None) -> list[OrderRecord]:
    sql = """
        SELECT order_id, contract_id, customer_id, order_date, due_date, status,
               service_id, order_revenue, estimated_cost, delivery_note
        FROM orders
    """
    params = None
    if contract_id is not None:
        sql += " WHERE contract_id = %s"
        params = (contract_id,)
    sql += " ORDER BY order_id"
    rows = query_db(sql, params)
    return [OrderRecord(**row) for row in require_rows(rows, "orders")]


@function_tool
def get_cashflows(month: str | None = None) -> list[CashflowRecord]:
    """Read monthly cashflow records from PostgreSQL."""
    return get_cashflows_impl(month)


@function_tool
def get_company_profiles(company_id: str | None = None) -> list[CompanyProfile]:
    """Read company profiles with organization and person identifiers masked."""
    return [
        mask_company_profile(item)
        for item in get_company_profiles_impl(company_id)
    ]


@function_tool
def get_contracts(contract_id: str | None = None) -> list[ContractRecord]:
    """Read contracts with contract and customer identifiers masked."""
    return [mask_contract(item) for item in get_contracts_impl(contract_id)]


@function_tool
def get_credit_profiles(company_id: str | None = None) -> list[CreditProfile]:
    """Read credit profiles with restricted identifiers masked."""
    return [
        mask_credit_profile(item)
        for item in get_credit_profiles_impl(company_id)
    ]


@function_tool
def get_orders(contract_id: str | None = None) -> list[OrderRecord]:
    """Read orders with order, contract, customer, and service IDs masked."""
    return [mask_order(item) for item in get_orders_impl(contract_id)]


if __name__ == "__main__":
    output = {
        "cashflows": [item.model_dump(mode="json") for item in get_cashflows_impl()],
        "companies": [
            item.model_dump(mode="json") for item in get_company_profiles_impl()
        ],
        "contracts": [item.model_dump(mode="json") for item in get_contracts_impl()],
        "credit_profiles": [
            item.model_dump(mode="json") for item in get_credit_profiles_impl()
        ],
        "orders": [item.model_dump(mode="json") for item in get_orders_impl()],
    }
    print(json.dumps(output, default=str, ensure_ascii=False, indent=2))
