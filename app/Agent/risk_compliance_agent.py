"""OpenAI Risk & Compliance Agent configuration."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from agents import Agent, OpenAIChatCompletionsModel, Runner

from app.Agent.config import OPENAI_CLIENT, OPENAI_MODEL
from app.Agent.hooks import AppContext, CustomAgentHooks
from app.Agent.prompts import RISK_COMPLIANCE_SYSTEM_PROMPT
from app.schema.handoff_packs import FinanceFeaturePack, RiskPack
from app.tools.RiskAgent import RISK_AGENT_TOOLS


Risk_compliance_agent = Agent(
    name="Risk_compliance_agent",
    model=OpenAIChatCompletionsModel(
        model=OPENAI_MODEL,
        openai_client=OPENAI_CLIENT,
    ),
    instructions=RISK_COMPLIANCE_SYSTEM_PROMPT,
    handoff_description=(
        "Evaluates a Finance Feature Pack against organizer-provided risk rules "
        "and returns a masked Risk Pack."
    ),
    tools=RISK_AGENT_TOOLS,
    output_type=RiskPack,
    hooks=CustomAgentHooks(display_name="Risk & Compliance Agent"),
)


async def main(finance_pack: FinanceFeaturePack) -> RiskPack:
    """Pass one Finance Feature Pack directly to Risk Agent."""
    finance_pack_json = finance_pack.model_dump_json()
    print(
        f"[INPUT] case_id={finance_pack.case_id} | "
        f"contract_id={finance_pack.contract_id}"
    )
    result = await Runner.run(
        Risk_compliance_agent,
        input=finance_pack_json,
        context=AppContext(
            document_id=finance_pack.contract_id,
            original_input=finance_pack_json,
            run_id=finance_pack.case_id,
        ),
        max_turns=3,
    )
    if not isinstance(result.final_output, RiskPack):
        raise TypeError("Risk Agent did not return a RiskPack.")
    risk_pack = result.final_output
    print("\n[FINAL RISK PACK]")
    print(risk_pack.model_dump_json(indent=2))
    return risk_pack


async def test_agents() -> None:
    finance_pack = FinanceFeaturePack(
        case_id="CASE-HEALTHY-001",
        contract_id="CON-HEALTHY-001",
        company_id="OPC-001",
        generated_at=datetime.now(UTC),
        transaction_risk_score=20,
        projected_closing_cash=800_000_000,
        cash_reserve_minimum=550_000_000,
        gross_margin=0.35,
        document_sent_to_partner=False,
        requested_amount=200_000_000,
        confidence_score=0.90,
        delivery_delay_days=0,
        source_record_ids=[
            "CON-HEALTHY-001",
            "TXN-HEALTHY-001",
        ],
    )
    await main(finance_pack)


__all__ = ["Risk_compliance_agent", "main", "test_agents"]


if __name__ == "__main__":
    asyncio.run(test_agents())
