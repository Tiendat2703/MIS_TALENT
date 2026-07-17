from dataclasses import dataclass, field
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DecisionStatus(str, Enum):
    APPROVE = "approve"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class DecisionCardOutput:
    """
    Kết quả cuối cùng của Decision & Partner Agent, đúng format đề bài yêu cầu:
    Decision Card = phương án + ba lý do + một điều kiện bảo vệ.
    """
    contract_id: str
    accept_opportunity: bool
    recommended_option: str
    protective_condition: str
    capital_need: float
    risk_level: RiskLevel
    decision_status: DecisionStatus
    reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    eligible_score: float | None = None
    precheck_note: str | None = None
    requires_founder_confirmation: bool = True
    approval_status: bool = False
    is_preliminary: bool = True

    def __post_init__(self) -> None:
        if self.approval_status:
            if self.eligible_score is None or self.precheck_note is None:
                raise ValueError(
                    "Approved precheck output requires eligible_score and precheck_note"
                )
        elif self.eligible_score is not None or self.precheck_note is not None:
            raise ValueError(
                "eligible_score and precheck_note must be None when approval_status is False"
            )


@dataclass(frozen=True, slots=True)
class DecisionBatchOutput:
    """Decision Cards for every contract submitted in one agent run."""

    decisions: list[DecisionCardOutput]



@dataclass(frozen=True, slots=True)
class DecisionAgentHandoff:
    """Validated payload passed from the Decision Agent to another agent."""
    user_request: str
    product_type: str
    recommended_product: str | None
    eligible: bool
    score: int
    note: str
    missing_information: list[str] = field(default_factory=list)
