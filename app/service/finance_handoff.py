"""Adapter from Finance's rich internal analysis to the canonical handoff pack."""

from __future__ import annotations

import re
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


_FUNDING_TERM_PATTERNS = (
    (
        "performance_bond",
        r"(?:performance|perormance|performace|performan)[\s_-]+bond"
        r"|bảo\s+lãnh\s+thực\s+hiện",
    ),
    (
        "working_capital",
        r"working[\s_-]+capital|vốn\s+lưu\s+động",
    ),
    (
        "trade_finance",
        r"trade[\s_-]+finance|tài\s+trợ\s+thương\s+mại|letter\s+of\s+credit"
        r"|(?<!\w)l\s*/?\s*c(?!\w)",
    ),
)


def resolve_funding_term_amount(
    payment_terms: str | None,
    contract_value: float | None,
) -> dict[str, Any] | None:
    """Resolve requested amount from an explicit financing term.

    An explicit amount or percentage next to the financing clause wins. When
    the clause contains neither, the agreed business fallback is 100% of the
    contract value. Percentages belonging to later payment milestones are not
    captured because they are not adjacent to the financing clause. This only
    resolves the amount; Decision still owns the banking need/product type.
    """
    if contract_value is None or contract_value <= 0:
        return None
    normalized = str(payment_terms or "").casefold().strip()
    matched_term = next(
        (
            (term_name, term_pattern)
            for term_name, term_pattern in _FUNDING_TERM_PATTERNS
            if re.search(term_pattern, normalized) is not None
        ),
        None,
    )
    if matched_term is None:
        return None
    term_name, term_pattern = matched_term

    percentage_patterns = (
        rf"(?:{term_pattern})\s*"
        rf"(?:(?:required|requires|requirement|yêu\s+cầu|nhu\s+cầu)\s*)?"
        rf"(?:[:=\-]\s*)?(\d+(?:[.,]\d+)?)\s*%",
        rf"(\d+(?:[.,]\d+)?)\s*%\s*(?:of\s+contract\s+value\s*)?"
        rf"(?:{term_pattern})",
    )
    for pattern in percentage_patterns:
        match = re.search(pattern, normalized)
        if match is None:
            continue
        percentage = float(match.group(1).replace(",", "."))
        if not 0 < percentage <= 100:
            continue
        return {
            "amount": round(contract_value * percentage / 100.0, 2),
            "source": "payment_terms_percentage",
            "status": "CALCULATED",
            "formula": f"contract_value × {percentage:g}%",
            "percentage": percentage,
            "term": term_name,
        }

    amount_pattern = (
        rf"(?:{term_pattern})\s*"
        r"(?:amount|value|giá\s+trị)?\s*[:=\-]?\s*"
        r"(\d[\d.,\s]*)\s*(vnd|vnđ|đồng|đ|triệu|tr)\b"
    )
    amount_match = re.search(amount_pattern, normalized)
    if amount_match is not None:
        raw_amount = amount_match.group(1).strip()
        unit = amount_match.group(2)
        if unit in {"triệu", "tr"}:
            amount = float(raw_amount.replace(" ", "").replace(",", ".")) * 1_000_000
        else:
            amount = float(re.sub(r"[.,\s]", "", raw_amount))
        if amount > 0:
            return {
                "amount": round(amount, 2),
                "source": "payment_terms_explicit_amount",
                "status": "EXTRACTED",
                "formula": "explicit financing amount in payment_terms",
                "percentage": None,
                "term": term_name,
            }

    return {
        "amount": contract_value,
        "source": "payment_terms_full_contract_fallback",
        "status": "ESTIMATED",
        "formula": "contract_value × 100%",
        "percentage": 100.0,
        "term": term_name,
    }


def resolve_performance_bond_amount(
    payment_terms: str | None,
    contract_value: float | None,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper restricted to performance-bond terms."""
    result = resolve_funding_term_amount(payment_terms, contract_value)
    if result is None or result.get("term") != "performance_bond":
        return None
    return result


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

    # Finance owns the amount, not the banking form. Explicit input wins. For a
    # financing clause, use its stated amount/rate or the agreed 100% of
    # contract-value fallback. Only ordinary payment terms continue to use the
    # cashflow deficit.
    explicit_requested_amount = _optional_float(contract.get("requested_amount"))
    cashflow_requested_amount = _optional_float(
        cash_impact.get("peak_contract_cash_deficit") if cash_impact else None
    )
    if cashflow_requested_amount is not None and cashflow_requested_amount <= 0:
        cashflow_requested_amount = None
    term_amount = resolve_funding_term_amount(
        contract.get("payment_terms"),
        contract_value,
    )
    if explicit_requested_amount is not None:
        requested_amount = explicit_requested_amount
        requested_amount_source = "contract"
        requested_amount_status = "PROVIDED"
        requested_amount_formula = None
    elif term_amount is not None:
        requested_amount = float(term_amount["amount"])
        requested_amount_source = str(term_amount["source"])
        requested_amount_status = str(term_amount["status"])
        requested_amount_formula = str(term_amount["formula"])
    else:
        requested_amount = cashflow_requested_amount
        requested_amount_source = (
            "contract_cashflow_peak_deficit"
            if cashflow_requested_amount is not None
            else "missing"
        )
        requested_amount_status = (
            "CALCULATED" if cashflow_requested_amount is not None else "MISSING"
        )
        requested_amount_formula = (
            "max(0, -min(cumulative contract inflows - outflows))"
            if cashflow_requested_amount is not None
            else None
        )
    if cash_impact is not None:
        cash_impact["requested_financing_amount"] = requested_amount

    # Finance passes through a legacy/user-provided value only. New submissions
    # leave this null; Decision chooses the banking form from payment_terms.
    funding_need_type = contract.get("funding_need_type")

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
        requested_amount=requested_amount,
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
            f"requested_amount={requested_amount}. "
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
                "source": "contract" if funding_need_type else "decision_required",
                "requested_amount_source": requested_amount_source,
                "requested_amount_status": requested_amount_status,
                "requested_amount_formula": requested_amount_formula,
                "requested_amount_percentage": (
                    term_amount.get("percentage") if term_amount else None
                ),
                "requested_amount_term": (
                    term_amount.get("term") if term_amount else None
                ),
                "performance_bond_percentage": (
                    term_amount.get("percentage")
                    if term_amount and term_amount.get("term") == "performance_bond"
                    else None
                ),
            },
            "description": contract.get("description"),
        },
    )


__all__ = [
    "build_finance_handoff",
    "infer_funding_need_type",
    "resolve_funding_term_amount",
    "resolve_performance_bond_amount",
]
