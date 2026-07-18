"""Adapter from Finance's rich internal analysis to the canonical handoff pack."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schema.financeAgent import FinanceAnalysisPack
from app.schema.handoff_packs import FinanceFeaturePack
from app.tools.FinanceAgent.contract_impact import analyze_contract_cashflow_impact


def _funding_need_type(payment_terms: str) -> str:
    normalized = payment_terms.casefold()
    if "performance bond" in normalized:
        return "PERFORMANCE_BOND"
    if "lc" in normalized or "trade finance" in normalized:
        return "TRADE_FINANCE"
    return "WORKING_CAPITAL"


def build_finance_handoff(
    contract_id: str,
    analysis: FinanceAnalysisPack,
    source_data: dict[str, Any],
) -> FinanceFeaturePack:
    contract = next(
        (
            item
            for item in source_data.get("contracts", [])
            if item.get("contract_id") == contract_id
        ),
        None,
    )
    if contract is None:
        raise LookupError(f"Finance source does not contain contract_id={contract_id}")

    orders = [
        item
        for item in source_data.get("orders", [])
        if item.get("contract_id") == contract_id
    ]
    order_ids = {str(item.get("order_id")) for item in orders if item.get("order_id")}
    invoices = [
        item
        for item in source_data.get("invoices", [])
        if str(item.get("order_id")) in order_ids
    ]
    customer = next(
        (
            item
            for item in source_data.get("customers", [])
            if item.get("customer_id") == contract.get("customer_id")
        ),
        {},
    )

    liquidity_months = analysis.liquidity_brief.by_month
    lowest_month = min(
        liquidity_months,
        key=lambda item: item.projected_closing_cash,
        default=None,
    )
    contract_margin = next(
        (
            item
            for item in analysis.margin_analysis.by_contract
            if item.get("contract_id") == contract_id
        ),
        None,
    )
    # What-if dòng tiền: chỉ tính cho hợp đồng MỚI vừa upload (chưa nằm trong
    # cashflow gốc). Hợp đồng có sẵn trong danh mục thì tác động đã phản ánh ở
    # cashflow rồi nên để None.
    upload = source_data.get("upload") or {}
    cash_impact = None
    if upload.get("contract_id") == contract_id:
        cash_impact = analyze_contract_cashflow_impact(
            upload,
            [
                {
                    "month": month.month,
                    "projected_closing_cash": month.projected_closing_cash,
                    "cash_reserve_minimum": month.cash_reserve_minimum,
                }
                for month in liquidity_months
            ],
        )

    source_record_ids = [contract_id]
    source_record_ids.extend(sorted(order_ids))
    source_record_ids.extend(
        str(item["invoice_id"])
        for item in invoices
        if item.get("invoice_id")
    )
    receivable_list = [
        str(item["invoice_id"])
        for item in invoices
        if item.get("invoice_id")
        and str(item.get("status", "")).casefold() != "paid"
    ]

    return FinanceFeaturePack(
        case_id=f"CASE-{contract_id}",
        contract_id=contract_id,
        company_id=str(source_data.get("profile", {}).get("company_id") or "UNKNOWN"),
        generated_at=datetime.now(UTC),
        transaction_risk_score=contract.get("transaction_risk_score"),
        projected_closing_cash=(
            lowest_month.projected_closing_cash if lowest_month else None
        ),
        cash_reserve_minimum=(
            lowest_month.cash_reserve_minimum if lowest_month else None
        ),
        gross_margin=(
            float(contract_margin["margin_pct"])
            if contract_margin and contract_margin.get("margin_pct") is not None
            else (
                float(contract["gross_margin"])
                if contract.get("gross_margin") is not None
                else None
            )
        ),
        document_sent_to_partner=contract.get("document_sent_to_partner"),
        contract_value=(
            float(contract["contract_value"])
            if contract.get("contract_value") is not None
            else None
        ),
        requested_amount=(
            float(contract["requested_amount"])
            if contract.get("requested_amount") is not None
            else analysis.liquidity_brief.funding_need
        ),
        confidence_score=contract.get("confidence_score"),
        delivery_delay_days=contract.get("delivery_delay_days"),
        funding_need_type=(
            contract.get("funding_need_type")
            or _funding_need_type(str(contract.get("payment_terms") or ""))
        ),
        tenor=(
            str(contract.get("tenor"))
            if contract.get("tenor")
            else (
                f"{contract.get('start_date')} to {contract.get('end_date')}"
                if contract.get("start_date") and contract.get("end_date")
                else None
            )
        ),
        customer_type=(
            str(customer.get("customer_type")) if customer.get("customer_type") else None
        ),
        supplier_docs=[],
        receivable_list=receivable_list,
        source_record_ids=source_record_ids,
        handoff_summary=analysis.handoff_summary,
        status=analysis.status,
        cash_impact=cash_impact,
        finance_details={
            "contract_margin": contract_margin,
            "contract_status": contract.get("status"),
            "payment_terms": contract.get("payment_terms"),
            "description": contract.get("description"),
        },
    )


__all__ = ["build_finance_handoff"]
