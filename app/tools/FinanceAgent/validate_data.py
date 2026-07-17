"""Bước 1 — Load & validate.

Kiểm tra toàn vẹn tham chiếu, field bắt buộc, số bất thường, và phân loại
counterparty của bank_txn. Điểm quan trọng: KHÔNG coi mọi counterparty là
khách hàng — SUP-/TAX/FOUNDER là bên ngoài hợp lệ, UNK- là tín hiệu rủi ro
chứ không phải lỗi dữ liệu.
"""

from __future__ import annotations

from app.schema.financeAgent import ValidationIssue, ValidationResult
from app.tools.FinanceAgent.util import to_float


def _looks_like_customer(cp) -> bool:
    return isinstance(cp, str) and cp.startswith("CUS-")


def validate_finance_data(data: dict) -> ValidationResult:
    contracts = data["contracts"]
    orders = data["orders"]
    invoices = data["invoices"]
    bank_txn = data["bank_txn"]
    cashflow = data["cashflow"]

    customer_ids = {c.get("customer_id") for c in data["customers"]}
    contract_ids = {c.get("contract_id") for c in contracts}
    order_ids = {o.get("order_id") for o in orders}

    issues: list[ValidationIssue] = []

    # --- Toàn vẹn tham chiếu ---
    for c in contracts:
        if c.get("customer_id") not in customer_ids:
            issues.append(ValidationIssue("broken_reference", "04_CONTRACTS", c.get("contract_id", "?"),
                                          f"customer_id {c.get('customer_id')} không tồn tại", "error"))
    for o in orders:
        if o.get("contract_id") not in contract_ids:
            issues.append(ValidationIssue("broken_reference", "06_ORDERS", o.get("order_id", "?"),
                                          f"contract_id {o.get('contract_id')} không tồn tại", "error"))
        if o.get("customer_id") not in customer_ids:
            issues.append(ValidationIssue("broken_reference", "06_ORDERS", o.get("order_id", "?"),
                                          f"customer_id {o.get('customer_id')} không tồn tại", "error"))
    for i in invoices:
        if i.get("order_id") not in order_ids:
            issues.append(ValidationIssue("broken_reference", "07_INVOICES", i.get("invoice_id", "?"),
                                          f"order_id {i.get('order_id')} không tồn tại", "error"))
        if i.get("customer_id") not in customer_ids:
            issues.append(ValidationIssue("broken_reference", "07_INVOICES", i.get("invoice_id", "?"),
                                          f"customer_id {i.get('customer_id')} không tồn tại", "error"))

    # --- Field bắt buộc + số bất thường ---
    for c in contracts:
        if c.get("contract_value") is None:
            issues.append(ValidationIssue("missing_field", "04_CONTRACTS", c.get("contract_id", "?"), "thiếu contract_value", "warning"))
    for o in orders:
        rev = o.get("order_revenue")
        if rev is None:
            issues.append(ValidationIssue("missing_field", "06_ORDERS", o.get("order_id", "?"), "thiếu order_revenue", "warning"))
        elif to_float(rev) <= 0:
            issues.append(ValidationIssue("numeric", "06_ORDERS", o.get("order_id", "?"), "order_revenue <= 0", "warning"))
        if o.get("estimated_cost") is None:
            issues.append(ValidationIssue("missing_field", "06_ORDERS", o.get("order_id", "?"), "thiếu estimated_cost", "warning"))
    for i in invoices:
        if i.get("invoice_amount") is None:
            issues.append(ValidationIssue("missing_field", "07_INVOICES", i.get("invoice_id", "?"), "thiếu invoice_amount", "warning"))
        if not i.get("due_date"):
            issues.append(ValidationIssue("missing_field", "07_INVOICES", i.get("invoice_id", "?"), "thiếu due_date", "warning"))
    for cf in cashflow:
        if cf.get("projected_closing_cash") is None:
            issues.append(ValidationIssue("missing_field", "09_CASHFLOW", cf.get("month", "?"), "thiếu projected_closing_cash", "error"))
        if cf.get("cash_reserve_minimum") is None:
            issues.append(ValidationIssue("missing_field", "09_CASHFLOW", cf.get("month", "?"), "thiếu cash_reserve_minimum", "error"))

    # --- Phân loại counterparty ---
    customer_cp, external_cp, unidentified_cp = set(), set(), set()
    for t in bank_txn:
        cp = t.get("counterparty_id")
        if _looks_like_customer(cp):
            if cp in customer_ids:
                customer_cp.add(cp)
            else:
                unidentified_cp.add(cp)
                issues.append(ValidationIssue("unidentified_counterparty", "08_BANK_TXN", t.get("txn_id", "?"),
                                              f"counterparty {cp} dạng khách hàng nhưng không có trong master", "warning"))
        elif isinstance(cp, str) and cp.startswith("UNK"):
            unidentified_cp.add(cp)
            issues.append(ValidationIssue("unidentified_counterparty", "08_BANK_TXN", t.get("txn_id", "?"),
                                          f"counterparty {cp} chưa định danh", "warning"))
        elif cp:
            external_cp.add(cp)   # SUP-, TAX, FOUNDER... hợp lệ, không phải lỗi

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    readiness = "Insufficient" if error_count else ("Conditional" if warning_count else "Ready")

    return ValidationResult(
        readiness=readiness,
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
        customer_counterparties=sorted(customer_cp),
        external_counterparties=sorted(external_cp),
        unidentified_counterparties=sorted(unidentified_cp),
    )
