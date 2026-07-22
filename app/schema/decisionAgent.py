"""Strict structured output for the Decision Agent."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.schema.handoff_packs import Severity, StrictModel


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
    CONTINUE_AS_PLANNED = "CONTINUE_AS_PLANNED"
    CONTINUE_WITH_ACTIONS = "CONTINUE_WITH_ACTIONS"
    ESCALATE_FOR_REVIEW = "ESCALATE_FOR_REVIEW"
    RECOMMEND_RENEGOTIATION = "RECOMMEND_RENEGOTIATION"
    RECOMMEND_HOLD = "RECOMMEND_HOLD"
    NEED_MORE_DATA = "NEED_MORE_DATA"


ACTIVE_RECOMMENDED_OPTIONS = frozenset({
    RecommendedOption.CONTINUE_AS_PLANNED,
    RecommendedOption.CONTINUE_WITH_ACTIONS,
    RecommendedOption.ESCALATE_FOR_REVIEW,
    RecommendedOption.RECOMMEND_RENEGOTIATION,
    RecommendedOption.RECOMMEND_HOLD,
    RecommendedOption.NEED_MORE_DATA,
})


class ManagementAction(StrictModel):
    action: str = Field(min_length=1)
    owner: str = Field(min_length=1)


class ApprovalFlow(StrictModel):
    required: bool = False
    source: str | None = None
    status: Literal[
        "NOT_REQUIRED",
        "NOT_REQUESTED",
        "PENDING",
        "APPROVED",
        "REJECTED",
        "EXECUTED",
    ] = "NOT_REQUIRED"
    object_ids: list[str] = Field(default_factory=list)


class DecisionCardOutput(StrictModel):
    """Decision-only projection.

    Raw warnings and missing evidence remain authoritative in FinanceFeaturePack
    and RiskPack.  They are intentionally not copied into this LLM-produced
    card, which prevents stale or hallucinated duplicates.
    """

    contract_id: str = Field(min_length=1)
    # ACTIVE reviews set this legacy new-opportunity field to null because they
    # recommend how to manage an existing contract rather than accept/reject it.
    accept_opportunity: bool | None
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
    # Null means Risk did not have enough governed evidence to conclude a level.
    risk_level: RiskLevel | None = None
    risk_assessment_status: Literal["COMPLETE", "INCOMPLETE"] = "COMPLETE"
    review_priority: Severity | None = None
    decision_status: DecisionStatus
    reasons: list[str] = Field(min_length=3, max_length=3)
    eligibility_score: float | None = Field(default=None, ge=0, le=100)
    # Historical input aliases remain accepted while new JSON output omits the
    # ambiguous legacy fields.
    eligible_score: SkipJsonSchema[float | None] = Field(
        default=None, ge=0, le=100, exclude=True
    )
    precheck_note: str | None = None
    requires_founder_confirmation: bool = True
    human_confirmation_status: Literal[
        "PENDING", "CONFIRMED", "NOT_REQUIRED"
    ] = "PENDING"
    portfolio_transaction_approval: ApprovalFlow = Field(
        default_factory=ApprovalFlow
    )
    contract_final_action_approval: ApprovalFlow = Field(
        default_factory=ApprovalFlow
    )
    external_api_submission_approval: ApprovalFlow = Field(
        default_factory=ApprovalFlow
    )
    external_api_submission_approval_status: Literal[
        "NOT_REQUESTED", "PENDING", "APPROVED", "REJECTED", "EXECUTED"
    ] = "NOT_REQUESTED"
    bank_precheck_status: Literal[
        "NOT_ELIGIBLE_TO_RUN",
        "ELIGIBLE_AWAITING_APPROVAL",
        "PENDING",
        "COMPLETED",
        "FAILED",
    ] = "NOT_ELIGIBLE_TO_RUN"
    approval_status: SkipJsonSchema[bool | None] = Field(default=None, exclude=True)
    is_preliminary: bool = True
    # Lifecycle fields are required by the ongoing ACTIVE-contract branch but
    # optional for historical/new-contract cards to preserve compatibility.
    contract_status: str | None = None
    assessment_type: Literal[
        "NEW_CONTRACT_REVIEW",
        "ONGOING_CONTRACT_REVIEW",
    ] | None = None
    required_actions: list[ManagementAction] = Field(default_factory=list)
    human_confirmation_points: list[str] = Field(default_factory=list)
    is_final_decision: Literal[False] = False

    @model_validator(mode="after")
    def validate_precheck_state(self) -> "DecisionCardOutput":
        if (
            self.eligibility_score is not None
            and self.eligible_score is not None
            and self.eligibility_score != self.eligible_score
        ):
            raise ValueError("eligibility_score conflicts with legacy eligible_score")
        resolved_score = (
            self.eligibility_score
            if self.eligibility_score is not None
            else self.eligible_score
        )
        object.__setattr__(self, "eligibility_score", resolved_score)
        object.__setattr__(self, "eligible_score", resolved_score)
        if self.approval_status is True:
            if self.external_api_submission_approval_status == "NOT_REQUESTED":
                object.__setattr__(
                    self,
                    "external_api_submission_approval_status",
                    "EXECUTED",
                )
            if self.bank_precheck_status == "NOT_ELIGIBLE_TO_RUN":
                object.__setattr__(self, "bank_precheck_status", "COMPLETED")

        external_required = (
            self.external_api_submission_approval_status != "NOT_REQUESTED"
        )
        object.__setattr__(
            self,
            "external_api_submission_approval",
            ApprovalFlow(
                required=external_required,
                source="BANK_PRECHECK" if external_required else None,
                status=(
                    self.external_api_submission_approval_status
                    if external_required
                    else "NOT_REQUIRED"
                ),
                object_ids=list(
                    self.external_api_submission_approval.object_ids
                ),
            ),
        )

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
            if self.accept_opportunity is not False:
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
        normalized_status = (self.contract_status or "").strip().casefold()
        is_active_review = (
            normalized_status == "active"
            or self.assessment_type == "ONGOING_CONTRACT_REVIEW"
        )
        if is_active_review:
            if normalized_status != "active":
                raise ValueError(
                    "ONGOING_CONTRACT_REVIEW requires contract_status=ACTIVE"
                )
            if self.assessment_type != "ONGOING_CONTRACT_REVIEW":
                raise ValueError(
                    "ACTIVE contract requires assessment_type=ONGOING_CONTRACT_REVIEW"
                )
            if self.recommended_option not in ACTIVE_RECOMMENDED_OPTIONS:
                raise ValueError(
                    "ACTIVE contract must use an ongoing-contract recommendation"
                )
            if self.decision_status is not DecisionStatus.REVIEW:
                raise ValueError(
                    "ACTIVE contract recommendation requires decision_status=review"
                )
            if self.accept_opportunity is not None:
                raise ValueError(
                    "ACTIVE contract must not accept or reject a new opportunity"
                )
            if not self.is_preliminary or not self.requires_founder_confirmation:
                raise ValueError(
                    "ACTIVE contract recommendation must remain preliminary and human-gated"
                )
            if not self.human_confirmation_points:
                raise ValueError(
                    "ACTIVE contract recommendation requires a human confirmation point"
                )
            if (
                self.recommended_option
                in {
                    RecommendedOption.CONTINUE_WITH_ACTIONS,
                    RecommendedOption.ESCALATE_FOR_REVIEW,
                    RecommendedOption.RECOMMEND_RENEGOTIATION,
                    RecommendedOption.RECOMMEND_HOLD,
                    RecommendedOption.NEED_MORE_DATA,
                }
                and not self.required_actions
            ):
                raise ValueError(
                    "This ACTIVE recommendation requires at least one management action"
                )
        elif self.recommended_option in ACTIVE_RECOMMENDED_OPTIONS:
            raise ValueError(
                "Ongoing-contract recommendation requires an ACTIVE contract review"
            )
        if self.risk_assessment_status == "INCOMPLETE":
            if self.risk_level is not None:
                raise ValueError(
                    "INCOMPLETE risk assessment requires risk_level=null"
                )
            if self.review_priority is None:
                raise ValueError(
                    "INCOMPLETE risk assessment requires review_priority"
                )
            # An incomplete Risk Pack is a hard precheck gate only while
            # governing an existing ACTIVE contract. For a new/non-ACTIVE
            # opportunity it remains visible evidence, but must not block a
            # human-gated bank precheck request or its approved execution.
            if is_active_review:
                if self.external_api_submission_approval_status != "NOT_REQUESTED":
                    raise ValueError(
                        "Incomplete ACTIVE risk cannot request external API approval"
                    )
                if self.bank_precheck_status != "NOT_ELIGIBLE_TO_RUN":
                    raise ValueError(
                        "Incomplete ACTIVE risk is not eligible to run a bank precheck"
                    )
        if self.requires_founder_confirmation:
            if self.human_confirmation_status == "NOT_REQUIRED":
                raise ValueError(
                    "Required human confirmation cannot have status NOT_REQUIRED"
                )
        elif self.human_confirmation_status != "NOT_REQUIRED":
            raise ValueError(
                "human_confirmation_status must be NOT_REQUIRED when confirmation is not required"
            )

        precheck_completed = (
            self.external_api_submission_approval_status == "EXECUTED"
            and self.bank_precheck_status == "COMPLETED"
        )
        if precheck_completed:
            if self.eligibility_score is None or not (self.precheck_note or "").strip():
                raise ValueError(
                    "Completed precheck output requires eligibility_score and precheck_note"
                )
        elif self.eligibility_score is not None or self.precheck_note is not None:
            raise ValueError(
                "eligibility_score and precheck_note must be null before precheck completion"
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
    "ApprovalFlow",
    "DecisionBatchOutput",
    "DecisionCardOutput",
    "DecisionStatus",
    "ACTIVE_RECOMMENDED_OPTIONS",
    "ManagementAction",
    "RecommendedOption",
    "RiskLevel",
]
