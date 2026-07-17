"""Public handoff contracts for the Risk & Compliance Agent."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FinanceFeaturePack(StrictModel):
    """Handoff from Data & Finance Agent to Risk Agent."""

    case_id: str
    contract_id: str
    company_id: str
    generated_at: datetime
    transaction_risk_score: int | None = Field(default=None, ge=0, le=100)
    projected_closing_cash: float | None = None
    cash_reserve_minimum: float | None = None
    gross_margin: float | None = None
    document_sent_to_partner: bool | None = None
    requested_amount: float | None = None
    confidence_score: float | None = Field(default=None, ge=0, le=1)
    delivery_delay_days: int | None = Field(default=None, ge=0)
    source_record_ids: list[str] = Field(default_factory=list)


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
    decision_made_by_risk_agent: Literal[False] = False


__all__ = [
    "FinanceFeaturePack",
    "MaskedDataSummary",
    "MaskedField",
    "ProposedAlert",
    "RiskAlert",
    "RiskAlertMatch",
    "RiskFinding",
    "RiskPack",
    "RiskPackSummary",
    "RuleEvaluation",
    "Severity",
    "StrictModel",
]
