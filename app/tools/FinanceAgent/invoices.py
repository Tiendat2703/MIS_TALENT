"""Bước 4 — Phân loại invoice.

overdue KHÔNG phải một status có sẵn (data chỉ có Paid/Open/Not issued) mà phải
tự suy ra = status Open và due_date đã qua ngày tham chiếu. Không suy 'đã phát
hành' từ việc có sẵn issue_date; chỉ dựa vào status.
"""

from __future__ import annotations

from datetime import date

from app.schema.financeAgent import InvoiceClassification
from app.tools.FinanceAgent.util import parse_date, to_float


def classify_invoices(invoices: list[dict], today: date | None = None) -> InvoiceClassification:
    today = today or date.today()
    buckets = {"paid": [], "open_current": [], "overdue": [], "not_issued": []}

    for inv in invoices:
        status = str(inv.get("status", "")).strip().lower()
        row = {
            "invoice_id": inv.get("invoice_id"),
            "customer_id": inv.get("customer_id"),
            "order_id": inv.get("order_id"),
            "amount": to_float(inv.get("invoice_amount")),
            "due_date": inv.get("due_date"),
            "status": inv.get("status"),
        }
        if status == "paid":
            buckets["paid"].append(row)
        elif status == "not issued":
            buckets["not_issued"].append(row)
        elif status == "open":
            due = parse_date(inv.get("due_date"))
            if due and due < today:
                row["days_overdue"] = (today - due).days
                buckets["overdue"].append(row)
            else:
                buckets["open_current"].append(row)
        else:
            # status lạ -> xếp tạm vào open_current để không bỏ sót
            buckets["open_current"].append(row)

    def total(key: str) -> float:
        return sum(r["amount"] for r in buckets[key])

    return InvoiceClassification(
        paid_total=total("paid"),
        open_current_total=total("open_current"),
        overdue_total=total("overdue"),
        not_issued_total=total("not_issued"),
        buckets=buckets,
    )
