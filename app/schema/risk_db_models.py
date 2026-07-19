"""Internal models used to map PostgreSQL rows for Risk Agent tools."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schema.handoff_packs import (
    RiskAlertMatch,
    RuleEvaluation,
    Severity,
    StrictModel,
)


class RiskRule(StrictModel):
    rule_id: str = Field(pattern=r"^RR-\d{3}$")
    risk_type: str
    trigger_condition: str
    severity: Severity
    required_action: str
    owner_agent: str


class BankTransaction(StrictModel):
    txn_id: str
    txn_date: date | None = None
    bank: str | None = None
    account_id: str | None = None
    direction: str | None = None
    description: str | None = None
    amount: Decimal | None = None
    counterparty_id: str | None = None
    txn_status: str | None = None
    transaction_risk_score: int | None = Field(default=None, ge=0, le=100)


class CashflowRecord(StrictModel):
    month: str
    expected_cash_in: Decimal | None = None
    expected_cash_out: Decimal | None = None
    direct_cost: Decimal | None = None
    opex: Decimal | None = None
    cash_reserve_minimum: Decimal | None = None
    projected_closing_cash: Decimal | None = None
    management_note: str | None = None


class CompanyProfile(StrictModel):
    company_id: str
    company_name: str | None = None
    business_model: str | None = None
    founder: str | None = None
    headquarter: str | None = None
    current_regions: str | None = None
    target_regions: str | None = None
    core_services: str | None = None
    operating_constraint: str | None = None
    governance_rule: str | None = None
    cash_reserve_minimum: Decimal | None = None
    target_gross_margin: Decimal | None = None
    late_delivery_penalty_rate: Decimal | None = None


class ContractRecord(StrictModel):
    contract_id: str
    customer_id: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = None
    description: str | None = None
    contract_value: Decimal | None = None
    gross_margin: Decimal | None = None
    payment_terms: str | None = None


class CreditProfile(StrictModel):
    credit_case_id: str
    company_id: str | None = None
    request_type: str | None = None
    requested_amount: Decimal | None = None
    tenor: str | None = None
    collateral_or_basis: str | None = None
    eligibility_score: Decimal | None = None
    precheck_note: str | None = None
    approval_status: str | None = None


class OrderRecord(StrictModel):
    order_id: str
    contract_id: str | None = None
    customer_id: str | None = None
    order_date: date | None = None
    due_date: date | None = None
    status: str | None = None
    service_id: str | None = None
    order_revenue: Decimal | None = None
    estimated_cost: Decimal | None = None
    delivery_note: str | None = None


class DataClassRule(StrictModel):
    data_pattern: str
    example_field: str | None = None
    classification: str | None = None
    external_api_rule: str | None = None
    masking_or_tokenization: str | None = None
    logging_rule: str | None = None


class MaskingExample(StrictModel):
    source_field: str
    raw_example: str | None = None
    masked_example: str | None = None
    tokenized_example: str | None = None
    allowed_for_partner_api: str | None = None
    reason: str | None = None


class RiskEvaluationReport(StrictModel):
    evaluated_at: datetime
    evaluations: list[RuleEvaluation]
    triggered_rule_ids: list[str]
    human_approval_required: bool
    source_tables: list[str]


class RiskReport(StrictModel):
    generated_at: datetime
    evaluation: RiskEvaluationReport
    alert_matches: list[RiskAlertMatch]
    data_classes: list[DataClassRule]
    masking_examples: list[MaskingExample]
    decision_made_by_risk_agent: Literal[False] = False


__all__ = [
    "BankTransaction",
    "CashflowRecord",
    "CompanyProfile",
    "ContractRecord",
    "CreditProfile",
    "DataClassRule",
    "MaskingExample",
    "OrderRecord",
    "RiskEvaluationReport",
    "RiskReport",
    "RiskRule",
]
