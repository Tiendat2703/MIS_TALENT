"""Bước 2 — Đối chiếu invoice với bank transaction.

Chống đếm trùng: một invoice chỉ khớp một txn và ngược lại, và bắt buộc
invoice_id phải xuất hiện trong description (vì INV-001 và INV-003 cùng khách
CUS-001, cùng 45M — nếu chỉ so số tiền + khách sẽ khớp nhầm cả hai vào TXN-004).
Chỉ credit direction=Credit, txn_status=Normal, counterparty là khách hàng mới
được coi là tiền thu công nợ. Loại góp vốn founder và giao dịch đáng ngờ.
"""

from __future__ import annotations

from app.schema.financeAgent import BankReconciliationSummary
from app.tools.FinanceAgent.util import money, to_float

AMOUNT_TOLERANCE = 1000  # VND, cho phép lệch nhỏ khi khớp


def _is_credit(t: dict) -> bool:
    return str(t.get("direction", "")).strip().lower() == "credit"


def _is_customer_cp(cp) -> bool:
    return isinstance(cp, str) and cp.startswith("CUS-")


def reconcile(invoices: list[dict], bank_txn: list[dict]) -> BankReconciliationSummary:
    credits = [t for t in bank_txn if _is_credit(t)]

    matched: list[dict] = []
    used_txn: set[str] = set()
    matched_invoice: set[str] = set()

    # Chỉ invoice Paid/Open mới có thể có tiền về (Not issued thì không).
    candidates = [inv for inv in invoices if str(inv.get("status", "")).strip().lower() in ("paid", "open")]

    for inv in candidates:
        inv_id = inv.get("invoice_id")
        cust = inv.get("customer_id")
        amt = to_float(inv.get("invoice_amount"))
        for t in credits:
            if t.get("txn_id") in used_txn:
                continue
            if str(t.get("txn_status")) != "Normal":
                continue
            if t.get("counterparty_id") != cust:
                continue
            if abs(to_float(t.get("amount")) - amt) > AMOUNT_TOLERANCE:
                continue
            if str(inv_id) not in str(t.get("description", "")):
                continue  # token invoice_id — mấu chốt chống khớp nhầm
            matched.append({"invoice_id": inv_id, "txn_id": t.get("txn_id"), "amount": amt})
            used_txn.add(t.get("txn_id"))
            matched_invoice.add(inv_id)
            break

    confirmed_total = sum(m["amount"] for m in matched)

    # Invoice Open chưa có tiền về (gồm cả overdue vì status vẫn là Open)
    open_without_cash_in = [
        inv.get("invoice_id") for inv in invoices
        if str(inv.get("status", "")).strip().lower() == "open" and inv.get("invoice_id") not in matched_invoice
    ]

    # Invoice ghi Paid nhưng không có txn khớp -> bất nhất, cần soi
    paid_without_txn = [
        inv.get("invoice_id") for inv in invoices
        if str(inv.get("status", "")).strip().lower() == "paid" and inv.get("invoice_id") not in matched_invoice
    ]

    # Phân loại các credit còn lại
    unmatched_customer_credits: list[dict] = []
    non_operating_credits: list[dict] = []
    suspicious_credits: list[dict] = []
    for t in credits:
        if t.get("txn_id") in used_txn:
            continue
        row = {"txn_id": t.get("txn_id"), "counterparty_id": t.get("counterparty_id"),
               "amount": to_float(t.get("amount")), "description": t.get("description")}
        if str(t.get("txn_status")) != "Normal":
            suspicious_credits.append(row)
        elif _is_customer_cp(t.get("counterparty_id")):
            unmatched_customer_credits.append(row)
        else:
            non_operating_credits.append(row)  # FOUNDER, ...

    note_parts = [f"Confirmed cash (khớp invoice) = {money(confirmed_total)}."]
    if non_operating_credits:
        note_parts.append(f"{len(non_operating_credits)} credit ngoài hoạt động (vd góp vốn) không tính là doanh thu.")
    if unmatched_customer_credits:
        note_parts.append(f"{len(unmatched_customer_credits)} credit của khách chưa gắn invoice.")
    if paid_without_txn:
        note_parts.append(f"Invoice ghi Paid nhưng chưa thấy giao dịch khớp: {', '.join(paid_without_txn)}.")

    return BankReconciliationSummary(
        confirmed_cash_total=confirmed_total,
        matched=matched,
        open_without_cash_in=open_without_cash_in,
        unmatched_customer_credits=unmatched_customer_credits,
        non_operating_credits=non_operating_credits,
        suspicious_credits=suspicious_credits,
        note=" ".join(note_parts),
    )
