"""Masking cho Risk Agent, lái theo policy 20_DATA_CLASS.

- Hàm module-level (`tokenize_identifier`, `mask_text_identifiers`, `mask_alert`,
  `mask_example`) giữ nguyên cho các tool đọc dữ liệu (GetRiskControls) và service.
- `Masker` là bản policy-driven: khởi tạo từ `list[DataClassRule]`, phân loại field
  theo 20_DATA_CLASS, mask đúng cách theo classification, và GHI LẠI các field đã
  mask để dựng section `masked_data` trong RiskPack.
"""

from __future__ import annotations

import hashlib
import re

from app.schema.handoff_packs import MaskedField, RiskAlert
from app.schema.risk_db_models import DataClassRule, MaskingExample

# Token định danh dạng PREFIX-XXXX trong chuỗi tự do (vd "TXN-006, CON-004").
_IDENTIFIER = re.compile(
    r"\b(?:TXN|CON|CR|ORD|INV|CUS|ACC|OPC|SUP|UNK)[-_][A-Z0-9]+\b",
    re.I,
)

# Prefix định danh -> classification (khớp tinh thần 20_DATA_CLASS).
_PREFIX_CLASSIFICATION = {
    "CUS": "restricted", "ACC": "restricted", "OPC": "restricted",
    "TXN": "restricted", "SUP": "restricted", "UNK": "restricted",
    "CON": "internal", "ORD": "internal", "INV": "internal", "CR": "internal",
}

# Field tài chính nhạy cảm (business confidential) — tên metric trong pack khác với
# example_field của 20_DATA_CLASS nên map bổ sung ở đây.
_CONFIDENTIAL_FIELDS = {
    "projected_closing_cash", "closing_cash", "cash_reserve_minimum",
    "gross_margin", "expected_gross_margin_rate",
    "allocated_order_estimated_margin_rate", "actual_margin_rate",
    "requested_amount", "contract_value", "cashflow",
    "eligibility_score",
}

# Tên field -> prefix token, theo quy ước tổ chức (vd account_id -> TOK-ACC-...,
# customer_id -> TOK-CUS-...). Dùng khi biết tên field, để prefix theo LOẠI field
# thay vì theo prefix của giá trị.
_FIELD_TOKEN_PREFIX = {
    "account_id": "ACC",
    "customer_id": "CUS",
    "counterparty_id": "CPT",
    "company_id": "ORG",
    "contract_id": "CON",
    "order_id": "ORD",
    "invoice_id": "INV",
    "txn_id": "TXN",
    "transaction_id": "TXN",
    "credit_case_id": "CR",
}


def tokenize_identifier(value: str, prefix: str | None = None) -> str:
    """Token hóa deterministic. prefix: nếu truyền thì dùng làm tiền tố (theo loại
    field, vd 'ACC'); nếu không thì suy từ tiền tố của chính giá trị."""
    if not prefix:
        prefix = value.split("-", 1)[0].split("_", 1)[0]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8].upper()
    return f"TOK-{prefix.upper()}-{digest}"


def mask_text_identifiers(value: str | None) -> str | None:
    if value is None:
        return None
    return _IDENTIFIER.sub(lambda match: tokenize_identifier(match.group(0)), value)


def mask_alert(alert: RiskAlert) -> RiskAlert:
    """Bản đơn giản (không policy, không ghi log) cho tool đọc alert."""
    safe = alert.model_copy(deep=True)
    safe.related_record = mask_text_identifiers(safe.related_record)
    return safe


def mask_example(example: MaskingExample) -> MaskingExample:
    """Ẩn giá trị raw của masking example trước khi trả ra ngoài."""
    safe = example.model_copy(deep=True)
    if safe.raw_example is not None:
        safe.raw_example = "[REDACTED]"
    return safe


class Masker:
    """Masking lái theo 20_DATA_CLASS, có ghi lại field đã mask."""

    def __init__(self, data_classes: list[DataClassRule] | None = None):
        self._field_class: dict[str, str] = {}
        self._action: dict[str, str] = {}
        for dc in data_classes or []:
            classification = (dc.classification or "").strip().lower()
            for field in (dc.example_field or "").split(","):
                name = field.strip().lower()
                if name:
                    self._field_class[name] = classification
            if classification:
                self._action[classification] = dc.masking_or_tokenization or ""
        self.masked_fields: list[MaskedField] = []
        self._seen: set[tuple[str, str]] = set()

    # -- phân loại --
    def classify_field(self, field_name: str) -> str:
        name = field_name.strip().lower()
        if name in self._field_class:
            return self._field_class[name]
        if name in _CONFIDENTIAL_FIELDS:
            return "confidential"
        return "internal"

    def _record(self, field_name: str, classification: str, masked_value: str) -> None:
        key = (field_name, masked_value)
        if key in self._seen:
            return
        self._seen.add(key)
        self.masked_fields.append(
            MaskedField(
                field_name=field_name,
                classification=classification,
                masked_value=masked_value,
            )
        )

    # -- mask giá trị field --
    def mask_field_value(self, field_name: str, value) -> str | None:
        if value is None:
            return None
        classification = self.classify_field(field_name)
        if classification == "restricted-secret":
            masked = "[SECRET]"
        elif classification == "confidential":
            masked = "[CONFIDENTIAL_VALUE]"
        elif classification == "restricted":
            masked = tokenize_identifier(
                str(value), _FIELD_TOKEN_PREFIX.get(field_name.strip().lower())
            )
        else:
            return str(value)  # internal/public: không mask giá trị
        self._record(field_name, classification, masked)
        return masked

    # -- mask identifier trong chuỗi tự do (vd related_record) --
    def mask_identifier_text(self, value: str | None, field_label: str = "identifier") -> str | None:
        if value is None:
            return None

        def repl(match: re.Match) -> str:
            token = match.group(0)
            prefix = token.split("-", 1)[0].split("_", 1)[0].upper()
            classification = _PREFIX_CLASSIFICATION.get(prefix, "restricted")
            masked = tokenize_identifier(token)
            self._record(field_label, classification, masked)
            return masked

        return _IDENTIFIER.sub(repl, value)

    def mask_alert(self, alert: RiskAlert) -> RiskAlert:
        safe = alert.model_copy(deep=True)
        safe.related_record = self.mask_identifier_text(safe.related_record, "related_record")
        return safe
