"""Backward-compatible prompt exports.

New code should call :func:`app.Agent.prompt_loader.load_prompt` directly.
"""

from app.Agent.prompt_loader import load_prompt

RISK_COMPLIANCE_SYSTEM_PROMPT = load_prompt("riskAgent.md")

__all__ = ["RISK_COMPLIANCE_SYSTEM_PROMPT"]
