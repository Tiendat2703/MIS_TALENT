"""Tiện ích dùng chung cho Finance Agent: parse ngày, ép kiểu số, format tiền."""

from __future__ import annotations

from datetime import date, datetime, timedelta

_EXCEL_EPOCH = date(1899, 12, 30)


def parse_date(value) -> date | None:
    """Chuẩn hóa ngày về datetime.date từ nhiều định dạng nguồn:
    - date/datetime (DB trả về)
    - chuỗi ISO 'YYYY-MM-DD' (mock)
    - số serial Excel (phòng khi đọc thẳng file)
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return _EXCEL_EPOCH + timedelta(days=int(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def to_float(value, default: float = 0.0) -> float:
    """Ép về float an toàn, trả default nếu None hoặc không parse được."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value) -> str:
    """Format tiền VND cho log dễ đọc, ví dụ 710000000 -> '710,000,000'."""
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)
