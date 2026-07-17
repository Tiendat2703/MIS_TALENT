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
    governance_threshold: float = 0.0
    requires_human_approval: bool = False


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


# ============ Bước 6: Missing data ============
@dataclass
class MissingDataItem:
    related_table: str
    related_record: str
    missing_item: str
    business_impact: str
    priority: str      # High | Medium | Low


# ============ Bước 7: LLM synthesis (output_type của Agent) ============
@dataclass(frozen=True)
class FinanceSynthesis:
    """Phần DUY NHẤT do LLM sinh. LLM chỉ diễn giải dựa trên số đã tính,
    không được tạo hay sửa bất kỳ con số nào."""
    finance_readiness_status: str          # Ready | Conditional | Insufficient
    liquidity_pressure_level: str          # Low | Medium | High
    data_confidence: str                   # Low | Medium | High
    margin_interpretation: str
    risk_agent_attention_points: list[str]
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
    financial_capacity_signals: dict       # cờ từ code + mức từ LLM
    handoff_summary: str
    agent_run_log: list[dict] = field(default_factory=list)
