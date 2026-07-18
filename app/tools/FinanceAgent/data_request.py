"""Form yêu cầu bổ sung dữ liệu còn thiếu.

- build_data_request_form: từ kết quả validate (các trường đang null) dựng ra form
  để người dùng điền. Mỗi field ứng với một bản ghi + cột THẬT đang thiếu, không
  bịa thêm.
- apply_form_submission: áp giá trị người dùng điền vào dữ liệu. Trường nào người
  dùng KHÔNG điền thì vẫn để thiếu (không tự suy ra). Trường nào sai kiểu thì báo
  invalid chứ không đoán.
"""

from __future__ import annotations

from app.schema.financeAgent import MissingDataField, MissingDataForm, ValidationResult
from app.tools.FinanceAgent.finance_data import PRIMARY_KEYS
from app.tools.FinanceAgent.util import parse_date, to_float

# Bảng theo tên sheet (trong ValidationIssue) -> khóa bảng trong data dict.
_SHEET_TO_TABLE = {
    "04_CONTRACTS": "contracts",
    "06_ORDERS": "orders",
    "07_INVOICES": "invoices",
    "08_BANK_TXN": "bank_txn",
    "09_CASHFLOW": "cashflow",
}

# Cột -> (data_type, nhãn hiển thị).
_COLUMN_META = {
    "projected_closing_cash": ("number", "Tiền mặt cuối kỳ dự kiến (VND)"),
    "cash_reserve_minimum": ("number", "Mức tiền dự trữ tối thiểu (VND)"),
    "contract_value": ("number", "Giá trị hợp đồng (VND)"),
    "order_revenue": ("number", "Doanh thu order (VND)"),
    "estimated_cost": ("number", "Chi phí ước tính (VND)"),
    "invoice_amount": ("number", "Số tiền hóa đơn (VND)"),
    "due_date": ("date", "Ngày đáo hạn (YYYY-MM-DD)"),
    "issue_date": ("date", "Ngày phát hành (YYYY-MM-DD)"),
    "paid_date": ("date", "Ngày thanh toán (YYYY-MM-DD)"),
}


def _make_field_id(table: str, record: str, column: str) -> str:
    return f"{table}|{record}|{column}"


def build_data_request_form(validation: ValidationResult, run_id: str | None = None) -> MissingDataForm:
    """Dựng form từ các issue kind='missing_field' của validate."""
    fields: list[MissingDataField] = []
    seen: set[str] = set()
    for issue in validation.issues:
        if issue.kind != "missing_field" or not issue.column:
            continue
        table = _SHEET_TO_TABLE.get(issue.table)
        if table is None:
            continue
        field_id = _make_field_id(table, issue.record, issue.column)
        if field_id in seen:
            continue
        seen.add(field_id)
        data_type, label = _COLUMN_META.get(issue.column, ("text", issue.column))
        fields.append(MissingDataField(
            field_id=field_id,
            table=table,
            record=issue.record,
            column=issue.column,
            label=f"{label} — {issue.record}",
            data_type=data_type,
            reason=issue.detail,
            required=(issue.severity == "error"),
        ))

    suffix = (run_id or "X")[:8]
    return MissingDataForm(
        form_id=f"FORM-{suffix}",
        title="Yêu cầu bổ sung dữ liệu tài chính còn thiếu",
        description=("Agent phát hiện các trường sau đang thiếu trong dữ liệu đầu vào. "
                     "Vui lòng điền giá trị thật để agent tiếp tục phân tích. "
                     "Trường nào không điền sẽ tiếp tục được báo là còn thiếu."),
        fields=fields,
    )


def _cast(data_type: str, value):
    """Ép kiểu giá trị người dùng nhập; trả None nếu không hợp lệ (không đoán)."""
    if data_type == "number":
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
    if data_type == "date":
        d = parse_date(value)
        return d.isoformat() if d else None
    text = str(value).strip()
    return text or None


def _column_type(column: str) -> str:
    return _COLUMN_META.get(column, ("text", ""))[0]


def apply_form_submission(data: dict, submission: dict) -> dict:
    """Áp giá trị người dùng điền (submission = {field_id: value}) vào data.

    Sửa trực tiếp data (data được nạp mới mỗi lần chạy). Trả về báo cáo gồm những
    field đã điền, còn thiếu, và không hợp lệ. KHÔNG tự điền trường người dùng bỏ trống.
    """
    filled: list[str] = []
    still_missing: list[str] = []
    invalid: list[dict] = []

    for field_id, value in (submission or {}).items():
        parts = field_id.split("|", 2)
        if len(parts) != 3:
            invalid.append({"field_id": field_id, "why": "field_id sai định dạng"})
            continue
        table, record, column = parts

        if value is None or (isinstance(value, str) and value.strip() == ""):
            still_missing.append(field_id)  # người dùng không điền -> vẫn thiếu, không bịa
            continue

        rows = data.get(table)
        pk = PRIMARY_KEYS.get(table)
        if rows is None or pk is None:
            invalid.append({"field_id": field_id, "why": f"không có bảng {table}"})
            continue

        row = next((r for r in rows if str(r.get(pk)) == str(record)), None)
        if row is None:
            invalid.append({"field_id": field_id, "why": f"không tìm thấy bản ghi {record}"})
            continue

        casted = _cast(_column_type(column), value)
        if casted is None:
            invalid.append({"field_id": field_id, "why": "giá trị không hợp lệ"})
            continue

        row[column] = casted
        filled.append(field_id)

    return {"filled": filled, "still_missing": still_missing, "invalid": invalid}
