"""What-if: định lượng một hợp đồng MỚI làm dòng tiền OPC đổi bao nhiêu.

Dùng cho hợp đồng upload (chưa nằm trong cashflow gốc). Chồng lịch thu theo điều
khoản thanh toán (vd 30% advance / 50% delivery / 20% acceptance) và chi phí giao
hàng lên chuỗi projected_closing_cash gốc, rồi tính lại đáy tiền mặt và mức vốn
cần tăng thêm.

Nguyên tắc: KHÔNG bịa. Mọi con số suy từ chính field của hợp đồng (contract_value,
gross_margin, payment_terms, start/end date). Giả định (cách rải chi phí, cách gán
milestone theo tháng) được ghi rõ trong ``assumptions`` để biện luận được.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# Lịch thanh toán mặc định khi không đọc được từ payment_terms (được đánh dấu rõ).
_DEFAULT_SCHEDULE = [("advance", 0.30), ("delivery", 0.50), ("acceptance", 0.20)]


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _month_range(start: str, end: str) -> list[str]:
    """Danh sách 'YYYY-MM' từ tháng start đến tháng end (bao gồm hai đầu)."""
    s = date.fromisoformat(str(start))
    e = date.fromisoformat(str(end))
    months: list[str] = []
    year, month = s.year, s.month
    while (year, month) <= (e.year, e.month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def parse_payment_schedule(payment_terms: str) -> tuple[list[tuple[str, float]], str]:
    """Đọc các mốc '<pct>% <label>' từ điều khoản thanh toán.

    Trả về (schedule, source) với source='parsed' nếu đọc được và tổng ≈ 100%,
    ngược lại dùng lịch mặc định với source='default'.
    """
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*([A-Za-zÀ-ỹ]+)", payment_terms or "")
    schedule = [(label.lower(), float(pct) / 100.0) for pct, label in matches]
    total = sum(pct for _, pct in schedule)
    if schedule and abs(total - 1.0) <= 0.01:
        return schedule, "parsed"
    return list(_DEFAULT_SCHEDULE), "default"


def _delivery_index(schedule: list[tuple[str, float]]) -> int:
    """Vị trí mốc 'giao hàng' trong schedule (để rải chi phí sản xuất tới đó)."""
    for index, (label, _) in enumerate(schedule):
        if "deliver" in label or "giao" in label:
            return index
    return len(schedule) // 2  # không thấy nhãn -> lấy mốc giữa


def _assign_milestone_months(
    schedule: list[tuple[str, float]],
    active_months: list[str],
) -> list[int]:
    """Gán mỗi mốc vào một chỉ số tháng theo tỉ lệ dọc vòng đời hợp đồng."""
    n = len(active_months)
    m = len(schedule)
    if m == 1:
        return [0]
    return [round(k / (m - 1) * (n - 1)) for k in range(m)]


def analyze_contract_cashflow_impact(
    upload: dict[str, Any],
    base_months: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """So sánh dòng tiền OPC TRƯỚC và SAU khi nhận thêm hợp đồng.

    upload: dict hợp đồng (contract_value, gross_margin, payment_terms, start/end,
    requested_amount, tenor...). base_months: cashflow gốc dạng
    [{month, projected_closing_cash, cash_reserve_minimum}, ...] (đã sắp theo tháng).
    """
    if not base_months:
        return None
    contract_value = float(upload.get("contract_value") or 0.0)
    if contract_value <= 0:
        return None
    gross_margin = float(upload.get("gross_margin") or 0.0)
    total_cost = round(contract_value * (1.0 - gross_margin), 2)
    total_margin = round(contract_value - total_cost, 2)

    schedule, schedule_source = parse_payment_schedule(str(upload.get("payment_terms") or ""))
    active_months = _month_range(upload["start_date"], upload["end_date"])
    milestone_idx = _assign_milestone_months(schedule, active_months)
    delivery_idx = milestone_idx[_delivery_index(schedule)]

    # Thu theo milestone.
    inflow_by_month: dict[str, float] = {}
    payment_schedule: list[dict[str, Any]] = []
    for (label, pct), idx in zip(schedule, milestone_idx):
        month = active_months[idx]
        amount = round(contract_value * pct, 2)
        inflow_by_month[month] = inflow_by_month.get(month, 0.0) + amount
        payment_schedule.append(
            {"label": label, "pct": pct, "amount": amount, "month": month}
        )

    # Chi phí sản xuất: rải đều từ tháng đầu tới tháng giao hàng (chi phí phát sinh
    # trong lúc thực hiện, kết thúc ở mốc giao hàng).
    cost_months = active_months[: delivery_idx + 1] or active_months
    cost_per_month = round(total_cost / len(cost_months), 2)
    outflow_by_month = {month: cost_per_month for month in cost_months}

    # Delta ròng theo tháng trên toàn vòng đời hợp đồng.
    monthly_net: dict[str, float] = {}
    for month in active_months:
        monthly_net[month] = round(
            inflow_by_month.get(month, 0.0) - outflow_by_month.get(month, 0.0), 2
        )

    # Chồng lên cửa sổ cashflow gốc. projected_closing_cash là SỐ DƯ cuối kỳ nên
    # delta tháng M dịch số dư của M và mọi tháng sau (cộng dồn).
    window = [str(m["month"]) for m in base_months]
    window_set = set(window)
    cumulative = 0.0
    monthly_delta: list[dict[str, Any]] = []
    closing_before: dict[str, float] = {}
    closing_after: dict[str, float] = {}
    reserve_by_month: dict[str, float] = {}
    for row in base_months:
        month = str(row["month"])
        before = float(row["projected_closing_cash"])
        reserve = float(row.get("cash_reserve_minimum") or 0.0)
        cumulative = round(cumulative + monthly_net.get(month, 0.0), 2)
        after = round(before + cumulative, 2)
        closing_before[month] = before
        closing_after[month] = after
        reserve_by_month[month] = reserve
        monthly_delta.append(
            {
                "month": month,
                "inflow": inflow_by_month.get(month, 0.0),
                "outflow": outflow_by_month.get(month, 0.0),
                "net_delta": monthly_net.get(month, 0.0),
                "cumulative_delta": cumulative,
                "projected_closing_before": before,
                "projected_closing_after": after,
            }
        )

    in_horizon_net = round(sum(v for m, v in monthly_net.items() if m in window_set), 2)
    out_horizon_net = round(sum(v for m, v in monthly_net.items() if m not in window_set), 2)

    def _max_gap(closing: dict[str, float]) -> float:
        return round(
            max((reserve_by_month[m] - closing[m] for m in window), default=0.0), 2
        )

    def _worst(closing: dict[str, float]) -> dict[str, Any]:
        month = min(window, key=lambda m: closing[m])
        return {"month": month, "projected_closing_cash": closing[month]}

    max_gap_before = _max_gap(closing_before)
    max_gap_after = _max_gap(closing_after)
    months_negative_after = [m for m in window if closing_after[m] < 0]

    return {
        "contract_id": upload.get("contract_id"),
        "horizon_months": window,
        "contract_active_months": active_months,
        "total_revenue": contract_value,
        "total_cost": total_cost,
        "net_contract_margin": total_margin,
        "requested_financing_amount": (
            float(upload["requested_amount"])
            if upload.get("requested_amount") is not None
            else None
        ),
        "funding_need_type": upload.get("funding_need_type"),
        "payment_schedule": payment_schedule,
        "monthly_delta": monthly_delta,
        "in_horizon_net_delta": in_horizon_net,
        "out_of_horizon_net_delta": out_horizon_net,
        "worst_month_before": _worst(closing_before),
        "worst_month_after": _worst(closing_after),
        "max_reserve_gap_before": max_gap_before,
        "max_reserve_gap_after": max_gap_after,
        "additional_funding_need": round(max_gap_after - max_gap_before, 2),
        "months_negative_cash_after": months_negative_after,
        "assumptions": {
            "schedule_source": schedule_source,
            "cost_allocation": (
                "Chi phí = contract_value × (1 − gross_margin), rải đều từ tháng đầu "
                "đến tháng giao hàng."
            ),
            "milestone_mapping": (
                "Mốc thanh toán gán theo tỉ lệ dọc vòng đời hợp đồng (advance→đầu, "
                "delivery→giữa, acceptance→cuối)."
            ),
            "note_out_of_horizon": (
                "Delta ngoài cửa sổ cashflow gốc không đổi được số dư trong kỳ; xem "
                "out_of_horizon_net_delta."
            ),
        },
    }


__all__ = [
    "analyze_contract_cashflow_impact",
    "parse_payment_schedule",
]
