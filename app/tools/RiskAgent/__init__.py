"""Public tool surface for the Risk & Compliance Agent."""

from agents import Tool

from app.tools.RiskAgent.BuildRiskReport import build_risk_pack
from app.tools.RiskAgent.SaveRiskPack import save_risk_pack

RISK_AGENT_TOOLS: list[Tool] = [
    build_risk_pack,
    save_risk_pack,
]

__all__ = [
    "RISK_AGENT_TOOLS",
    "build_risk_pack",
    "save_risk_pack",
]
