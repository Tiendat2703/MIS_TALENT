"""Bước 5 — Phân tích margin.

margin = order_revenue - estimated_cost. Gộp theo hợp đồng và toàn danh mục.
Báo cả hai góc nhìn: full-book (mọi order) và committed-only (Delivered +
In progress) để phân biệt cái đã chốt với cái mới là kế hoạch. Có guard chia 0.
"""

from __future__ import annotations

from app.schema.financeAgent import MarginAnalysis
from app.tools.FinanceAgent.util import to_float

COMMITTED_STATUSES = {"delivered", "in progress"}


def _pct(margin: float, revenue: float) -> float:
    return round(margin / revenue, 4) if revenue > 0 else 0.0


def analyze_margin(orders: list[dict], contracts: list[dict],
                   profile: dict | None = None, services: list[dict] | None = None) -> MarginAnalysis:
    target = to_float((profile or {}).get("target_gross_margin"), 0.0)

    by_order: list[dict] = []
    contract_agg: dict[str, list[float]] = {}   # contract_id -> [revenue, cost]
    total_rev = total_cost = 0.0
    committed_rev = committed_margin = 0.0
    orders_missing_data: list[str] = []

    for o in orders:
        # Thiếu revenue hoặc cost -> KHÔNG bịa (không coi là 0), bỏ qua và ghi nhận.
        if o.get("order_revenue") is None or o.get("estimated_cost") is None:
            orders_missing_data.append(o.get("order_id"))
            continue
        rev = to_float(o.get("order_revenue"))
        cost = to_float(o.get("estimated_cost"))
        margin = rev - cost
        by_order.append({
            "order_id": o.get("order_id"),
            "contract_id": o.get("contract_id"),
            "status": o.get("status"),
            "revenue": rev,
            "cost": cost,
            "margin_amount": margin,
            "margin_pct": _pct(margin, rev),
        })
        total_rev += rev
        total_cost += cost

        agg = contract_agg.setdefault(o.get("contract_id"), [0.0, 0.0])
        agg[0] += rev
        agg[1] += cost

        if str(o.get("status", "")).strip().lower() in COMMITTED_STATUSES:
            committed_rev += rev
            committed_margin += margin

    portfolio_margin = total_rev - total_cost
    portfolio_pct = _pct(portfolio_margin, total_rev)

    by_contract: list[dict] = []
    low_margin: list[str] = []
    for cid, (rev, cost) in contract_agg.items():
        pct = _pct(rev - cost, rev)
        below = pct < target
        by_contract.append({
            "contract_id": cid,
            "revenue": rev,
            "cost": cost,
            "margin_amount": rev - cost,
            "margin_pct": pct,
            "below_target": below,
        })
        if below:
            low_margin.append(cid)

    return MarginAnalysis(
        portfolio_revenue=total_rev,
        portfolio_cost=total_cost,
        portfolio_margin_amount=portfolio_margin,
        portfolio_margin_pct=portfolio_pct,
        committed_revenue=committed_rev,
        committed_margin_pct=_pct(committed_margin, committed_rev),
        target_margin_pct=target,
        margin_gap=round(portfolio_pct - target, 4),
        margin_pressure_flag=portfolio_pct < target,
        by_contract=by_contract,
        by_order=by_order,
        low_margin_contracts=low_margin,
        orders_missing_data=orders_missing_data,
    )
