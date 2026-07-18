"""Bước 6 — Missing data request.

Bám điều kiện THẬT trong dữ liệu (không có bảng chứng từ/nghiệm thu nào cả), suy
ra cái thiếu từ: invoice Open không có tiền về, invoice Not-issued mà order chưa
Delivered, credit khách không gắn invoice, counterparty chưa định danh, và các
lỗi validate. business_impact/priority ở đây là mức mặc định do code đặt; LLM sẽ
bổ sung góc nhìn qua attention_points và handoff_summary.
"""

from __future__ import annotations

from app.schema.financeAgent import (
    BankReconciliationSummary,
    InvoiceClassification,
    MissingDataItem,
    ValidationResult,
)
from app.tools.FinanceAgent.util import money


def detect_missing_data(
    data: dict,
    reconciliation: BankReconciliationSummary,
    invoice_classification: InvoiceClassification,
    validation: ValidationResult,
) -> list[MissingDataItem]:
    items: list[MissingDataItem] = []
    orders_by_id = {o.get("order_id"): o for o in data["orders"]}

    # 1) Invoice Open (gồm overdue) chưa có giao dịch ngân hàng khớp
    matched_inv = {m["invoice_id"] for m in reconciliation.matched}
    for inv in data["invoices"]:
        if str(inv.get("status", "")).strip().lower() == "open" and inv.get("invoice_id") not in matched_inv:
            items.append(MissingDataItem(
                related_table="07_INVOICES",
                related_record=inv.get("invoice_id"),
                missing_item="Chưa có giao dịch ngân hàng xác nhận đã thu",
                business_impact=f"Ảnh hưởng giả định thu {money(inv.get('invoice_amount'))} công nợ",
                priority="High",
            ))

    # 2) Invoice Not-issued mà order chưa Delivered -> chưa đủ cơ sở phát hành
    for inv in data["invoices"]:
        if str(inv.get("status", "")).strip().lower() == "not issued":
            order = orders_by_id.get(inv.get("order_id"))
            order_status = str(order.get("status")) if order else "không tìm thấy"
            if order_status != "Delivered":
                items.append(MissingDataItem(
                    related_table="06_ORDERS",
                    related_record=inv.get("order_id"),
                    missing_item=f"Order đang '{order_status}', chưa đủ cơ sở phát hành invoice {inv.get('invoice_id')}",
                    business_impact=f"Ảnh hưởng khả năng phát hành {money(inv.get('invoice_amount'))}",
                    priority="Medium",
                ))

    # 3) Credit của khách nhưng không gắn invoice
    for c in reconciliation.unmatched_customer_credits:
        items.append(MissingDataItem(
            related_table="08_BANK_TXN",
            related_record=c.get("txn_id"),
            missing_item=f"Credit {money(c.get('amount'))} từ {c.get('counterparty_id')} không gắn invoice",
            business_impact="Thiếu liên kết chứng từ để ghi nhận đúng doanh thu/AR",
            priority="Medium",
        ))

    # 4) Counterparty chưa định danh
    for cp in validation.unidentified_counterparties:
        items.append(MissingDataItem(
            related_table="08_BANK_TXN",
            related_record=cp,
            missing_item="Counterparty chưa định danh",
            business_impact="Cần xác minh danh tính, có thể là giao dịch bất thường",
            priority="High",
        ))

    # 5) Lỗi validate nghiêm trọng (thiếu field bắt buộc / gãy tham chiếu)
    for issue in validation.issues:
        if issue.severity == "error":
            items.append(MissingDataItem(
                related_table=issue.table,
                related_record=issue.record,
                missing_item=issue.detail,
                business_impact="Dữ liệu bắt buộc thiếu hoặc không hợp lệ, chặn phân tích chắc chắn",
                priority="High",
            ))

    return items
