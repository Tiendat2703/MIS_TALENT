"""Strict structured output for the Decision Agent."""

from __future__ import annotations

from enum import Enum

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
