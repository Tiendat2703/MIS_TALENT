"""Risk Agent factory and standalone runner."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

from app.Agent.bus import event_bus
from app.Agent.hooks import AppContext, CustomAgentHooks
from app.Agent.prompt_loader import load_prompt
from app.database.context_store import (
    load_finance_pack,
    load_pipeline_context,
    validate_pipeline_schema,
)
from app.schema.handoff_packs import RiskBatchPack
from app.tools.pipeline import process_risk_context


AGENT_NAME = "Risk_Agent"
_STANDALONE_AGENT: Agent[AppContext] | None = None


def build_risk_agent(*, handoffs: Sequence[Any] = ()) -> Agent[AppContext]:
    from app.Agent.config import OPENAI_MODEL, get_openai_client

    prompt = load_prompt("riskAgent.md")
    if handoffs:
        prompt = prompt_with_handoff_instructions(prompt)
    return Agent(
        name=AGENT_NAME,
        model=OpenAIChatCompletionsModel(
            model=OPENAI_MODEL,
            openai_client=get_openai_client(),
        ),
        instructions=prompt,
        handoff_description=(
            "Reads FinanceBatchPack from context by session_id, evaluates all "
            "risk rules deterministically per contract, and persists RiskBatchPack."
        ),
        tools=[process_risk_context],
        output_type=RiskBatchPack,
        handoffs=list(handoffs),
        model_settings=ModelSettings(parallel_tool_calls=False),
        hooks=CustomAgentHooks(AGENT_NAME),
    )


def get_risk_agent() -> Agent[AppContext]:
    global _STANDALONE_AGENT
    if _STANDALONE_AGENT is None:
        _STANDALONE_AGENT = build_risk_agent()
    return _STANDALONE_AGENT


async def main(session_id: int) -> RiskBatchPack:
    """Run Risk for an existing Finance context row."""
    validate_pipeline_schema()
    finance_pack = load_finance_pack(session_id)
    agent_input = json.dumps(
        {"session_id": session_id},
        ensure_ascii=False,
    )
    context = AppContext(
        document_id=f"BATCH-{session_id}",
        original_input=agent_input,
        run_id=session_id,
        contract_id=(
            finance_pack.contract_ids[0]
            if len(finance_pack.contract_ids) == 1
            else None
        ),
        contract_ids=finance_pack.contract_ids,
    )
    result = await Runner.run(
        get_risk_agent(),
        input=agent_input,
        context=context,
        max_turns=4,
    )
    if not isinstance(result.final_output, RiskBatchPack):
        raise TypeError("Risk Agent did not return a RiskBatchPack")

    persisted = load_pipeline_context(session_id).risk_pack
    if persisted is None or persisted != result.final_output:
        raise ValueError("Risk final output does not match persisted context.risk_pack")

    await event_bus.emit(
        session_id,
        {
            "type": "risk_finished",
            "agent": AGENT_NAME,
            "task": "Risk Pack persisted",
            "status": "done",
            "data": persisted.model_dump(mode="json"),
        },
    )
    event_bus.persist_snapshot(session_id)
    try:
        from app.tools.writeLogs import persist_agent_stage_log

        persist_agent_stage_log(session_id, "risk", persisted)
    except Exception as exc:
        print(f"[risk] Could not persist RiskLogs: {type(exc).__name__}: {exc}")
    return persisted


async def test_agents() -> None:
    import os

    value = os.getenv("RISK_AGENT_TEST_SESSION_ID")
    if not value:
        raise RuntimeError("Set RISK_AGENT_TEST_SESSION_ID to an existing session")
    risk_pack = await main(int(value))
    print(risk_pack.model_dump_json(indent=2))


__all__ = [
    "AGENT_NAME",
    "build_risk_agent",
    "get_risk_agent",
    "main",
    "test_agents",
]


if __name__ == "__main__":
    asyncio.run(test_agents())
