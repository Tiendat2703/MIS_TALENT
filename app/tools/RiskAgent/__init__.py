"""Independently testable, DB-backed Risk Agent tools."""

from agents import Tool

from app.tools.RiskAgent.BuildRiskReport import build_risk_pack, build_risk_report
from app.tools.RiskAgent.EvaluateRisks import evaluate_risks
from app.tools.RiskAgent.GetBankTransactions import get_bank_transactions
from app.tools.RiskAgent.GetFinancialRiskData import (
    get_cashflows,
    get_company_profiles,
    get_contracts,
    get_credit_profiles,
    get_orders,
)
from app.tools.RiskAgent.GetRiskControls import (
    get_alerts,
    get_data_classes,
    get_masking_examples,
    get_risk_rules,
)

RISK_AGENT_TOOLS: list[Tool] = [
    build_risk_pack,
]

__all__ = [
    "RISK_AGENT_TOOLS",
    "build_risk_pack",
    "build_risk_report",
    "evaluate_risks",
    "get_alerts",
    "get_bank_transactions",
    "get_cashflows",
    "get_company_profiles",
    "get_contracts",
    "get_credit_profiles",
    "get_data_classes",
    "get_masking_examples",
    "get_orders",
    "get_risk_rules",
]
