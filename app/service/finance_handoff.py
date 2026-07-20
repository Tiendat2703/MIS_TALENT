"""Adapter from Finance's rich internal analysis to the canonical handoff pack."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schema.financeAgent import FinanceAnalysisPack
from app.schema.handoff_packs import FinanceFeaturePack
from app.tools.FinanceAgent.contract_impact import analyze_contract_cashflow_impact


def infer_funding_need_type(payment_terms: str) -> str | None:
    """Infer only an explicitly stated financing need from payment terms.

    Ordinary payment schedules such as monthly or milestone payments do not
    imply that the contract needs a loan.
    """
    normalized = payment_terms.casefold()
    if "performance bond" in normalized or "bảo lãnh thực hiện" in normalized:
        return "PERFORMANCE_BOND"
    if any(term in normalized for term in (
        "trade finance",
        "tài trợ thương mại",
        "letter of credit",
        " l/c",
        " lc",
    )):
        return "TRADE_FINANCE"
    if "working capital" in normalized or "vốn lưu động" in normalized:
        return "WORKING_CAPITAL"
    return None


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


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
    contract_value = _optional_float(contract.get("contract_value"))
    # ``gross_margin`` on FinanceFeaturePack describes the complete contract.
    # Order-derived margin remains useful, but it is a different scope and is
    # exposed explicitly under finance_details.order_allocation below.
    contract_gross_margin = _optional_float(contract.get("gross_margin"))
    if contract_gross_margin is None and contract_margin:
        contract_gross_margin = _optional_float(contract_margin.get("margin_pct"))

    allocated_order_revenue = _optional_float(
        contract_margin.get("revenue") if contract_margin else None
    )
    allocated_order_cost = _optional_float(
        contract_margin.get("cost") if contract_margin else None
    )
    allocated_order_margin = _optional_float(
        contract_margin.get("margin_amount") if contract_margin else None
    )
    allocated_order_margin_rate = _optional_float(
        contract_margin.get("margin_pct") if contract_margin else None
    )
    expected_contract_margin_amount = (
        contract_value * contract_gross_margin
        if contract_value is not None and contract_gross_margin is not None
        else None
    )
    unallocated_contract_value = (
        max(contract_value - allocated_order_revenue, 0.0)
        if contract_value is not None and allocated_order_revenue is not None
        else None
    )
    allocated_order_ratio = (
        allocated_order_revenue / contract_value
        if contract_value and allocated_order_revenue is not None
        else None
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

    explicit_funding_need_type = contract.get("funding_need_type")
    inferred_funding_need_type = infer_funding_need_type(
        str(contract.get("payment_terms") or "")
    )
    funding_need_type = explicit_funding_need_type or inferred_funding_need_type

    return FinanceFeaturePack(
        case_id=f"CASE-{contract_id}",
        contract_id=contract_id,
        company_id=str(source_data.get("profile", {}).get("company_id") or "UNKNOWN"),
        generated_at=datetime.now(UTC),
        contract_name=contract.get("description"),
        start_date=contract.get("start_date"),
        end_date=contract.get("end_date"),
        transaction_risk_score=contract.get("transaction_risk_score"),
        projected_closing_cash=(
            lowest_month.projected_closing_cash if lowest_month else None
        ),
        cash_reserve_minimum=(
            lowest_month.cash_reserve_minimum if lowest_month else None
        ),
        gross_margin=contract_gross_margin,
        document_sent_to_partner=contract.get("document_sent_to_partner"),
        contract_value=contract_value,
        # Never turn the portfolio liquidity gap into a contract request.  A
        # missing bond/credit amount is evidence to collect, not a number to infer.
        requested_amount=_optional_float(contract.get("requested_amount")),
        confidence_score=contract.get("confidence_score"),
        delivery_delay_days=contract.get("delivery_delay_days"),
        funding_need_type=funding_need_type,
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
        handoff_summary=(
            f"Contract {contract_id}: contract_value={contract_value}; "
            f"expected_gross_margin_rate={contract_gross_margin}; "
            f"allocated_order_revenue={allocated_order_revenue}; "
            f"requested_amount={_optional_float(contract.get('requested_amount'))}. "
            "Portfolio liquidity and reconciliation metrics are available only in "
            "FinanceBatchPack.portfolio_analysis and must not be treated as "
            "contract-specific amounts."
        ),
        status=analysis.status,
        cash_impact=cash_impact,
        finance_details={
            "contract_economics": {
                "contract_value": contract_value,
                "expected_gross_margin_rate": contract_gross_margin,
                "expected_gross_margin_amount": expected_contract_margin_amount,
            },
            "order_allocation": {
                "allocated_order_revenue": allocated_order_revenue,
                "allocated_order_cost": allocated_order_cost,
                "allocated_order_margin_amount": allocated_order_margin,
                "allocated_order_margin_rate": allocated_order_margin_rate,
                "allocated_order_ratio": allocated_order_ratio,
                "unallocated_contract_value": unallocated_contract_value,
            },
            # Backward-compatible raw aggregate.  Its revenue/margin fields are
            # order-scoped and must never replace contract_value.
            "contract_margin": contract_margin,
            "contract_status": contract.get("status"),
            "payment_terms": contract.get("payment_terms"),
            "funding_need": {
                "type": funding_need_type,
                "source": (
                    "contract"
                    if explicit_funding_need_type
                    else "payment_terms"
                    if inferred_funding_need_type
                    else "none"
                ),
            },
            "description": contract.get("description"),
        },
    )


__all__ = ["build_finance_handoff", "infer_funding_need_type"]
