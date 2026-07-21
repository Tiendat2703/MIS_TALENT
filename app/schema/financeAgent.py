"""Strict internal schemas for the Finance Agent.

Nguyên tắc: CODE tính ra mọi con số. LLM CHỈ sinh phần
diễn giải trong FinanceSynthesis (không trả lại con số). FinanceAnalysisPack là
bản phân tích rich nội bộ; adapter tạo FinanceFeaturePack contract-case công khai.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schema.handoff_packs import StrictModel


# ============ Bước 1: Validate ============
class ValidationIssue(StrictModel):
    kind: str          # missing_field | broken_reference | numeric | unidentified_counterparty
    table: str
    record: str
    detail: str
    severity: str      # info | warning | error
    column: str = ""   # tên cột thiếu (chỉ có với kind=missing_field), để dựng form


class ValidationResult(StrictModel):
    readiness: str     # Ready | Conditional | Insufficient (rule-based; LLM tinh chỉnh sau)
    error_count: int
    warning_count: int
    issues: list[ValidationIssue] = Field(default_factory=list)
    customer_counterparties: list[str] = Field(default_factory=list)
    external_counterparties: list[str] = Field(default_factory=list)
    unidentified_counterparties: list[str] = Field(default_factory=list)


# ============ Bước 2: Reconcile ============
class BankReconciliationSummary(StrictModel):
    confirmed_cash_total: float
    matched: list[dict[str, Any]] = Field(default_factory=list)
    open_without_cash_in: list[str] = Field(default_factory=list)
    unmatched_customer_credits: list[dict[str, Any]] = Field(default_factory=list)
    non_operating_credits: list[dict[str, Any]] = Field(default_factory=list)
    suspicious_credits: list[dict[str, Any]] = Field(default_factory=list)
    note: str = ""


# ============ Bước 3: Liquidity & funding need ============
class LiquidityMonth(StrictModel):
    month: str
    projected_closing_cash: float
    cash_reserve_minimum: float
    reserve_gap: float
    net_operating_flow: float


class LiquidityBrief(StrictModel):
    by_month: list[LiquidityMonth]
    max_reserve_gap: float
    minimum_liquidity_need: float
    funding_need: float
    months_below_reserve: list[str] = Field(default_factory=list)
    months_negative_cash: list[str] = Field(default_factory=list)
    months_missing_data: list[str] = Field(default_factory=list)


# ============ Bước 4: Phân loại invoice ============
class InvoiceClassification(StrictModel):
    paid_total: float
    open_current_total: float
    overdue_total: float
    not_issued_total: float
    buckets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


# ============ Bước 5: Margin ============
class MarginAnalysis(StrictModel):
    portfolio_revenue: float
    portfolio_cost: float
    portfolio_margin_amount: float
    portfolio_margin_pct: float
    committed_revenue: float
    committed_margin_pct: float
    target_margin_pct: float
    margin_gap: float
    margin_pressure_flag: bool
    by_contract: list[dict[str, Any]] = Field(default_factory=list)
    by_order: list[dict[str, Any]] = Field(default_factory=list)
    low_margin_contracts: list[str] = Field(default_factory=list)
    orders_missing_data: list[str] = Field(default_factory=list)


# ============ Bước 6: Missing data ============
class MissingDataItem(StrictModel):
    related_table: str
    related_record: str
    missing_item: str
    business_impact: str
    priority: str      # High | Medium | Low


# ============ Form yêu cầu bổ sung dữ liệu thiếu ============
class MissingDataField(StrictModel):
    """Một trường dữ liệu còn thiếu, cần người dùng điền. Sinh từ dữ liệu thật,
    không bịa: mỗi trường ứng với một bản ghi + một cột đang null."""
    field_id: str          # "table|record|column" — dùng khi submit lại
    table: str             # khóa bảng trong data (contracts/orders/invoices/...)
    record: str            # khóa bản ghi (vd ORD-004, 2026-08)
    column: str            # tên cột thiếu (vd estimated_cost)
    label: str             # nhãn hiển thị cho người dùng
    data_type: str         # number | date | text
    reason: str            # vì sao cần
    required: bool = True
    current_value: object | None = None


class MissingDataForm(StrictModel):
    form_id: str
    title: str
    description: str
    fields: list[MissingDataField] = Field(default_factory=list)


# ============ Bước 7: LLM synthesis (output_type của Agent) ============
class FinanceSynthesis(StrictModel):
    """Phần LLM sinh: CHỈ tóm tắt SỐ LIỆU tài chính bằng lời để bàn giao cho Risk.
    KHÔNG đánh giá rủi ro, KHÔNG kết luận readiness/mức áp lực/human-approval,
    KHÔNG khuyến nghị. Chỉ nêu lại con số đã tính."""
    handoff_summary: str


class FinancePreflightSynthesis(StrictModel):
    """Narrative-only output from the isolated Finance preflight agent."""

    summary: str


class FinancePreflightMissingField(StrictModel):
    field: str
    label: str
    reason: str
    data_type: Literal["text", "number", "date"]


class FinancePreflightDataIssue(StrictModel):
    table: str
    record: str
    reason: str
    severity: str
    kind: str


class FinancePreflightResult(StrictModel):
    status: Literal["RUNNING", "AWAITING_INPUT"]
    can_start_pipeline: bool
    session_id: int | None = None
    missing_fields: list[FinancePreflightMissingField] = Field(default_factory=list)
    data_issues: list[FinancePreflightDataIssue] = Field(default_factory=list)
    summary: str


# ============ Output cuối: Finance Feature Pack ============
class FinanceAnalysisPack(StrictModel):
    metadata: dict[str, Any]
    liquidity_brief: LiquidityBrief
    invoice_classification: InvoiceClassification
    bank_reconciliation_summary: BankReconciliationSummary
    margin_analysis: MarginAnalysis
    missing_data_request: list[MissingDataItem]
    key_facts: dict[str, Any]
    handoff_summary: str
    status: Literal["COMPLETE", "AWAITING_INPUT"] = "COMPLETE"
    data_request_form: MissingDataForm | None = None
    submission_report: dict[str, Any] | None = None
    agent_run_log: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "BankReconciliationSummary",
    "FinanceAnalysisPack",
    "FinancePreflightDataIssue",
    "FinancePreflightMissingField",
    "FinancePreflightResult",
    "FinancePreflightSynthesis",
    "FinanceSynthesis",
    "InvoiceClassification",
    "LiquidityBrief",
    "LiquidityMonth",
    "MarginAnalysis",
    "MissingDataField",
    "MissingDataForm",
    "MissingDataItem",
    "ValidationIssue",
    "ValidationResult",
]
