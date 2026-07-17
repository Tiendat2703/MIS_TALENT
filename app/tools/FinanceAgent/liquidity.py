"""Bước 3 — Liquidity & funding need (đã gộp bước tính projected closing cash cũ).

Không tính lại projected_closing_cash (data không tái tạo được và vốn là forecast
cho sẵn) — chỉ ĐỌC nó. reserve_gap và funding_need suy ra từ đó. Thêm
net_operating_flow = expected_cash_in - expected_cash_out để lộ tháng nào tự
thân hoạt động đã âm dòng tiền.
"""

from __future__ import annotations

from app.schema.financeAgent import LiquidityBrief, LiquidityMonth
from app.tools.FinanceAgent.util import to_float

# Ngưỡng theo governance_rule của OPC: quyết định tài chính > 300M cần human approval.
GOVERNANCE_APPROVAL_THRESHOLD = 300_000_000


def analyze_liquidity(cashflow: list[dict], profile: dict | None = None) -> LiquidityBrief:
    months: list[LiquidityMonth] = []
    for cf in cashflow:
        closing = to_float(cf.get("projected_closing_cash"))
        reserve = to_float(cf.get("cash_reserve_minimum"))
        gap = max(0.0, reserve - closing)
        net_flow = to_float(cf.get("expected_cash_in")) - to_float(cf.get("expected_cash_out"))
        months.append(LiquidityMonth(
            month=cf.get("month"),
            projected_closing_cash=closing,
            cash_reserve_minimum=reserve,
            reserve_gap=gap,
            net_operating_flow=net_flow,
        ))

    max_gap = max((m.reserve_gap for m in months), default=0.0)
    months_below_reserve = [m.month for m in months if m.reserve_gap > 0]
    months_negative_cash = [m.month for m in months if m.projected_closing_cash < 0]

    funding_need = max_gap  # hạn mức tối thiểu cần có sẵn

    return LiquidityBrief(
        by_month=months,
        max_reserve_gap=max_gap,
        minimum_liquidity_need=max_gap,
        funding_need=funding_need,
        months_below_reserve=months_below_reserve,
        months_negative_cash=months_negative_cash,
        governance_threshold=float(GOVERNANCE_APPROVAL_THRESHOLD),
        requires_human_approval=funding_need > GOVERNANCE_APPROVAL_THRESHOLD,
    )
