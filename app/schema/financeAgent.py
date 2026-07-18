"""Schema cho Finance Agent.

Nguyên tắc: CODE tính ra mọi con số (các dataclass phần A–F). LLM CHỈ sinh phần
diễn giải trong FinanceSynthesis (không trả lại con số). FinanceFeaturePack là
bản ráp cuối = số từ code + diễn giải từ LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ============ Bước 1: Validate ============
@dataclass
class ValidationIssue:
    kind: str          # missing_field | broken_reference | numeric | unidentified_counterparty
    table: str
    record: str
    detail: str
    severity: str      # info | warning | error
    column: str = ""   # tên cột thiếu (chỉ có với kind=missing_field), để dựng form


@dataclass
class ValidationResult:
    readiness: str     # Ready | Conditional | Insufficient (rule-based; LLM tinh chỉnh sau)
    error_count: int
    warning_count: int
    issues: list[ValidationIssue] = field(default_factory=list)
    customer_counterparties: list[str] = field(default_factory=list)
    external_counterparties: list[str] = field(default_factory=list)
    unidentified_counterparties: list[str] = field(default_factory=list)


# ============ Bước 2: Reconcile ============
@dataclass
class BankReconciliationSummary:
    confirmed_cash_total: float
    matched: list[dict] = field(default_factory=list)                 # invoice_id, txn_id, amount
    open_without_cash_in: list[str] = field(default_factory=list)     # invoice_id còn là AR
    unmatched_customer_credits: list[dict] = field(default_factory=list)  # credit khách không gắn invoice
    non_operating_credits: list[dict] = field(default_factory=list)   # góp vốn founder...
    suspicious_credits: list[dict] = field(default_factory=list)      # credit không Normal (loại khỏi confirmed)
    note: str = ""


# ============ Bước 3: Liquidity & funding need ============
@dataclass
class LiquidityMonth:
    month: str
    projected_closing_cash: float
    cash_reserve_minimum: float
    reserve_gap: float
    net_operating_flow: float


@dataclass
class LiquidityBrief:
    by_month: list[LiquidityMonth]
    max_reserve_gap: float
    minimum_liquidity_need: float
    funding_need: float
    months_below_reserve: list[str] = field(default_factory=list)
    months_negative_cash: list[str] = field(default_factory=list)
    months_missing_data: list[str] = field(default_factory=list)  # tháng thiếu projected_closing_cash -> bỏ qua, không bịa


# ============ Bước 4: Phân loại invoice ============
@dataclass
class InvoiceClassification:
    paid_total: float
    open_current_total: float
    overdue_total: float
    not_issued_total: float
    buckets: dict = field(default_factory=dict)   # {"paid": [...], "overdue": [...], ...}


# ============ Bước 5: Margin ============
@dataclass
class MarginAnalysis:
    portfolio_revenue: float
    portfolio_cost: float
    portfolio_margin_amount: float
    portfolio_margin_pct: float
    committed_revenue: float
    committed_margin_pct: float
    target_margin_pct: float
    margin_gap: float
    margin_pressure_flag: bool
    by_contract: list[dict] = field(default_factory=list)
    by_order: list[dict] = field(default_factory=list)
    low_margin_contracts: list[str] = field(default_factory=list)
    orders_missing_data: list[str] = field(default_factory=list)  # order thiếu revenue/cost -> bỏ qua, không bịa


# ============ Bước 6: Missing data ============
@dataclass
class MissingDataItem:
    related_table: str
    related_record: str
    missing_item: str
    business_impact: str
    priority: str      # High | Medium | Low


# ============ Form yêu cầu bổ sung dữ liệu thiếu ============
@dataclass
class MissingDataField:
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


@dataclass
class MissingDataForm:
    form_id: str
    title: str
    description: str
    fields: list[MissingDataField] = field(default_factory=list)


# ============ Bước 7: LLM synthesis (output_type của Agent) ============
@dataclass(frozen=True)
class FinanceSynthesis:
    """Phần LLM sinh: CHỈ tóm tắt SỐ LIỆU tài chính bằng lời để bàn giao cho Risk.
    KHÔNG đánh giá rủi ro, KHÔNG kết luận readiness/mức áp lực/human-approval,
    KHÔNG khuyến nghị. Chỉ nêu lại con số đã tính."""
    handoff_summary: str


# ============ Output cuối: Finance Feature Pack ============
@dataclass
class FinanceFeaturePack:
    metadata: dict
    liquidity_brief: LiquidityBrief
    invoice_classification: InvoiceClassification
    bank_reconciliation_summary: BankReconciliationSummary
    margin_analysis: MarginAnalysis
    missing_data_request: list[MissingDataItem]
    key_facts: dict                        # số liệu/sự thật cô đọng cho Risk (KHÔNG phán đoán)
    handoff_summary: str
    status: str = "COMPLETE"               # COMPLETE | AWAITING_INPUT (đang chờ điền form)
    data_request_form: MissingDataForm | None = None
    submission_report: dict | None = None  # kết quả áp dữ liệu người dùng vừa điền
    agent_run_log: list[dict] = field(default_factory=list)
