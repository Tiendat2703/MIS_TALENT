"""Strict structured output for the Decision Agent."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from app.schema.handoff_packs import StrictModel


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionStatus(str, Enum):
    APPROVE = "approve"
    REVIEW = "review"
    REJECT = "reject"


class RecommendedOption(str, Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITION = "APPROVE_WITH_CONDITION"
    TEMPORARY_REJECT_RISK = "TEMPORARY_REJECT_RISK"
    REJECT_MISSING_EVIDENCE = "REJECT_MISSING_EVIDENCE"
    NO_SUITABLE_PRODUCT = "NO_SUITABLE_PRODUCT"


class DecisionCardOutput(StrictModel):
    """Decision-only projection.

    Raw warnings and missing evidence remain authoritative in FinanceFeaturePack
    and RiskPack.  They are intentionally not copied into this LLM-produced
    card, which prevents stale or hallucinated duplicates.
    """

    contract_id: str = Field(min_length=1)
    accept_opportunity: bool
    recommended_option: RecommendedOption
    protective_condition: str = Field(min_length=1)
    # Null means the contract-specific bond/credit amount was not supplied.
    # Portfolio liquidity need must never be copied into this field.
    capital_need: float | None = Field(default=None, ge=0)
    # Finance owns capital_need. Decision owns the banking form and selected
    # catalog product after matching payment_terms against that amount.
    funding_need_type: Literal[
        "PERFORMANCE_BOND",
        "TRADE_FINANCE",
        "WORKING_CAPITAL",
        "RECEIVABLE_FINANCING",
    ] | None = None
    selected_bank_product_id: str | None = Field(default=None, min_length=1)
    selected_bank_product_name: str | None = Field(default=None, min_length=1)
    risk_level: RiskLevel
    decision_status: DecisionStatus
    reasons: list[str] = Field(min_length=3, max_length=3)
    eligible_score: float | None = Field(default=None, ge=0, le=100)
    precheck_note: str | None = None
    requires_founder_confirmation: bool = True
    approval_status: bool = False
    is_preliminary: bool = True

    @model_validator(mode="after")
    def validate_precheck_state(self) -> "DecisionCardOutput":
        selected_product_fields = (
            self.selected_bank_product_id,
            self.selected_bank_product_name,
        )
        if any(selected_product_fields) and not all(selected_product_fields):
            raise ValueError(
                "Selected bank product id and name must be supplied together"
            )
        if self.selected_bank_product_id is not None and self.funding_need_type is None:
            raise ValueError(
                "Selected bank product requires a Decision-owned funding_need_type"
            )
        if (
            self.recommended_option is RecommendedOption.NO_SUITABLE_PRODUCT
            and self.selected_bank_product_id is not None
        ):
            raise ValueError(
                "NO_SUITABLE_PRODUCT cannot contain a selected bank product"
            )
        if self.recommended_option is RecommendedOption.TEMPORARY_REJECT_RISK:
            if self.accept_opportunity:
                raise ValueError(
                    "Temporary risk rejection requires accept_opportunity=false"
                )
            if self.decision_status is not DecisionStatus.REJECT:
                raise ValueError(
                    "Temporary risk rejection requires decision_status=reject"
                )
            if not self.is_preliminary:
                raise ValueError(
                    "Temporary risk rejection must remain preliminary"
                )
        if self.approval_status:
            if self.eligible_score is None or not (self.precheck_note or "").strip():
                raise ValueError(
                    "Approved precheck output requires eligible_score and precheck_note"
                )
        elif self.eligible_score is not None or self.precheck_note is not None:
            raise ValueError(
                "eligible_score and precheck_note must be null when approval_status is false"
            )
        return self


class DecisionBatchOutput(StrictModel):
    decisions: list[DecisionCardOutput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_contracts(self) -> "DecisionBatchOutput":
        contract_ids = [item.contract_id for item in self.decisions]
        if len(contract_ids) != len(set(contract_ids)):
            raise ValueError("DecisionBatchOutput contains duplicate contract_id values")
        return self


__all__ = [
    "DecisionBatchOutput",
    "DecisionCardOutput",
    "DecisionStatus",
    "RecommendedOption",
    "RiskLevel",
]
