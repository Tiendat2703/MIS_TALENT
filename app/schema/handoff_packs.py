"""Strict public contracts shared by Finance, Risk, and Decision agents."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FinanceFeaturePack(StrictModel):
    """Contract-scoped handoff persisted in ``public.context.finance_pack``."""

    case_id: str
    contract_id: str
    company_id: str
    generated_at: datetime
    transaction_risk_score: int | None = Field(default=None, ge=0, le=100)
    projected_closing_cash: float | None = None
    cash_reserve_minimum: float | None = None
    gross_margin: float | None = None
    document_sent_to_partner: bool | None = None
    contract_value: float | None = None
    requested_amount: float | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    delivery_delay_days: int | None = Field(default=None, ge=0)
    funding_need_type: Literal[
        "PERFORMANCE_BOND",
        "TRADE_FINANCE",
        "WORKING_CAPITAL",
        "RECEIVABLE_FINANCING",
    ] | None = None
    tenor: str | None = None
    customer_type: str | None = None
    supplier_docs: list[str] = Field(default_factory=list)
    receivable_list: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    handoff_summary: str
    status: Literal["COMPLETE", "AWAITING_INPUT"] = "COMPLETE"
    finance_details: dict[str, Any] = Field(default_factory=dict)
    # What-if dòng tiền cho hợp đồng MỚI (chỉ có với hợp đồng upload). None nếu hợp
    # đồng đã nằm sẵn trong cashflow gốc.
    cash_impact: dict[str, Any] | None = None


class FinanceBatchPack(StrictModel):
    """All contract-scoped Finance packs produced in one pipeline run."""

    contract_ids: list[str] = Field(min_length=1)
    packs: list[FinanceFeaturePack] = Field(min_length=1)
    portfolio_analysis: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_contracts(self) -> "FinanceBatchPack":
        observed = [pack.contract_id for pack in self.packs]
        if observed != self.contract_ids:
            raise ValueError("FinanceBatchPack packs must match contract_ids in order")
        if len(observed) != len(set(observed)):
            raise ValueError("FinanceBatchPack contains duplicate contracts")
        return self


class PipelineHandoff(StrictModel):
    """The only payload allowed to cross an SDK handoff boundary."""

    session_id: int = Field(gt=0)


class RiskAlert(StrictModel):
    """Masked alert included in a Risk Pack."""

    alert_id: str
    alert_date: date | None = None
    alert_type: str | None = None
    related_record: str | None = None
    severity: Severity | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    recommended_action: str | None = None


class RiskFinding(StrictModel):
    rule_id: str
    risk_type: str
    severity: Severity
    trigger_condition: str
    required_action: str
    owner_agent: str
    source_table: str
    record_id: str
    observed_metric: str
    observed_value: str
    comparison_operator: str
    comparison_value: str
    human_approval_required: bool


class RuleEvaluation(StrictModel):
    rule_id: str
    status: Literal["TRIGGERED", "NOT_TRIGGERED", "INSUFFICIENT_EVIDENCE"]
    owner_agent: str = ""
    severity: Severity | None = None
    observed_value: str | None = None
    required_action: str = ""
    findings: list[RiskFinding] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    message: str = ""


class RiskAlertMatch(StrictModel):
    alert: RiskAlert
    matched_rule_ids: list[str] = Field(default_factory=list)
    match_basis: Literal["RELATED_RECORD", "EXACT_RISK_TYPE", "UNMAPPED"]


class ProposedAlert(StrictModel):
    """Alert proposed by the agent when a triggered rule has no matching alert in
    the organizer-provided alert table. Always flagged for human review."""

    proposed_alert_id: str
    rule_id: str
    risk_type: str
    severity: Severity | None = None
    recommended_action: str = ""
    reason_for_proposal: str = ""
    related_records: list[str] = Field(default_factory=list)
    requires_human_review: Literal[True] = True
    alert_source: Literal["AGENT_PROPOSED"] = "AGENT_PROPOSED"


class MaskedField(StrictModel):
    """One field masked at egress. Carries only the masked form, never the raw value."""

    field_name: str
    classification: str
    masked_value: str


class MaskedDataSummary(StrictModel):
    masking_applied: bool = True
    masking_policy_source: str = "20_DATA_CLASS"
    masked_fields: list[MaskedField] = Field(default_factory=list)


class RiskPackSummary(StrictModel):
    total_rules_triggered: int
    triggered_rule_ids: list[str] = Field(default_factory=list)
    total_alerts_detected: int
    total_proposed_alerts: int
    unmapped_rule_ids: list[str] = Field(default_factory=list)
    highest_severity: Severity | None = None
    human_review_required: bool


class RiskPack(StrictModel):
    """Handoff from Risk Agent to Decision & Partner Agent."""

    case_id: str
    contract_id: str
    generated_at: datetime
    overall_risk_level: Severity | None = None
    rule_evaluations: list[RuleEvaluation]
    triggered_rule_ids: list[str]
    alerts: list[RiskAlertMatch] = Field(default_factory=list)
    proposed_alerts: list[ProposedAlert] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    insufficient_evidence: list[str] = Field(default_factory=list)
    human_approval_required: bool
    masked_data: MaskedDataSummary | None = None
    summary: RiskPackSummary | None = None
    handoff_summary: str
    decision_made_by_risk_agent: Literal[False] = False


class RiskBatchPack(StrictModel):
    """Risk results for every Finance case in the same pipeline run."""

    contract_ids: list[str] = Field(min_length=1)
    packs: list[RiskPack] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contracts(self) -> "RiskBatchPack":
        observed = [pack.contract_id for pack in self.packs]
        if observed != self.contract_ids:
            raise ValueError("RiskBatchPack packs must match contract_ids in order")
        if len(observed) != len(set(observed)):
            raise ValueError("RiskBatchPack contains duplicate contracts")
        return self


__all__ = [
    "FinanceFeaturePack",
    "FinanceBatchPack",
    "MaskedDataSummary",
    "MaskedField",
    "PipelineHandoff",
    "ProposedAlert",
    "RiskAlert",
    "RiskAlertMatch",
    "RiskFinding",
    "RiskPack",
    "RiskBatchPack",
    "RiskPackSummary",
    "RuleEvaluation",
    "Severity",
    "StrictModel",
]
