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
            issues.append(ValidationIssue(
                kind="broken_reference",
                table="04_CONTRACTS",
                record=c.get("contract_id", "?"),
                detail=f"customer_id {c.get('customer_id')} không tồn tại",
                severity="error",
            ))
    for o in orders:
        if o.get("contract_id") not in contract_ids:
            issues.append(ValidationIssue(
                kind="broken_reference",
                table="06_ORDERS",
                record=o.get("order_id", "?"),
                detail=f"contract_id {o.get('contract_id')} không tồn tại",
                severity="error",
            ))
        if o.get("customer_id") not in customer_ids:
            issues.append(ValidationIssue(
                kind="broken_reference",
                table="06_ORDERS",
                record=o.get("order_id", "?"),
                detail=f"customer_id {o.get('customer_id')} không tồn tại",
                severity="error",
            ))
    for i in invoices:
        if i.get("order_id") not in order_ids:
            issues.append(ValidationIssue(
                kind="broken_reference",
                table="07_INVOICES",
                record=i.get("invoice_id", "?"),
                detail=f"order_id {i.get('order_id')} không tồn tại",
                severity="error",
            ))
        if i.get("customer_id") not in customer_ids:
            issues.append(ValidationIssue(
                kind="broken_reference",
                table="07_INVOICES",
                record=i.get("invoice_id", "?"),
                detail=f"customer_id {i.get('customer_id')} không tồn tại",
                severity="error",
            ))

    # --- Field bắt buộc + số bất thường ---
    # Các trường tính toán cốt lõi thiếu -> error (chặn), vì không được bịa số.
    for c in contracts:
        if c.get("contract_value") is None:
            issues.append(ValidationIssue(
                kind="missing_field",
                table="04_CONTRACTS",
                record=c.get("contract_id", "?"),
                detail="thiếu contract_value",
                severity="error",
                column="contract_value",
            ))
    for o in orders:
        rev = o.get("order_revenue")
        if rev is None:
            issues.append(ValidationIssue(
                kind="missing_field",
                table="06_ORDERS",
                record=o.get("order_id", "?"),
                detail="thiếu order_revenue",
                severity="error",
                column="order_revenue",
            ))
        elif to_float(rev) <= 0:
            issues.append(ValidationIssue(
                kind="numeric",
                table="06_ORDERS",
                record=o.get("order_id", "?"),
                detail="order_revenue <= 0",
                severity="warning",
            ))
        if o.get("estimated_cost") is None:
            issues.append(ValidationIssue(
                kind="missing_field",
                table="06_ORDERS",
                record=o.get("order_id", "?"),
                detail="thiếu estimated_cost",
                severity="error",
                column="estimated_cost",
            ))
    for i in invoices:
        if i.get("invoice_amount") is None:
            issues.append(ValidationIssue(
                kind="missing_field",
                table="07_INVOICES",
                record=i.get("invoice_id", "?"),
                detail="thiếu invoice_amount",
                severity="error",
                column="invoice_amount",
            ))
        if not i.get("due_date"):
            issues.append(ValidationIssue(
                kind="missing_field",
                table="07_INVOICES",
                record=i.get("invoice_id", "?"),
                detail="thiếu due_date",
                severity="warning",
                column="due_date",
            ))
    for cf in cashflow:
        if cf.get("projected_closing_cash") is None:
            issues.append(ValidationIssue(
                kind="missing_field",
                table="09_CASHFLOW",
                record=cf.get("month", "?"),
                detail="thiếu projected_closing_cash",
                severity="error",
                column="projected_closing_cash",
            ))
        if cf.get("cash_reserve_minimum") is None:
            issues.append(ValidationIssue(
                kind="missing_field",
                table="09_CASHFLOW",
                record=cf.get("month", "?"),
                detail="thiếu cash_reserve_minimum",
                severity="error",
                column="cash_reserve_minimum",
            ))

    # --- Phân loại counterparty ---
    customer_cp, external_cp, unidentified_cp = set(), set(), set()
    for t in bank_txn:
        cp = t.get("counterparty_id")
        if _looks_like_customer(cp):
            if cp in customer_ids:
                customer_cp.add(cp)
            else:
                unidentified_cp.add(cp)
                issues.append(ValidationIssue(
                    kind="unidentified_counterparty",
                    table="08_BANK_TXN",
                    record=t.get("txn_id", "?"),
                    detail=f"counterparty {cp} dạng khách hàng nhưng không có trong master",
                    severity="warning",
                ))
        elif isinstance(cp, str) and cp.startswith("UNK"):
            unidentified_cp.add(cp)
            issues.append(ValidationIssue(
                kind="unidentified_counterparty",
                table="08_BANK_TXN",
                record=t.get("txn_id", "?"),
                detail=f"counterparty {cp} chưa định danh",
                severity="warning",
            ))
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
