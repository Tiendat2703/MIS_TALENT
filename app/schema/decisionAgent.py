from dataclasses import dataclass, field
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

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
    reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    requires_founder_confirmation: bool = True
    is_preliminary: bool = True


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
