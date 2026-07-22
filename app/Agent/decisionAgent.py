"""Decision Agent factory and standalone runner.

The integrated pipeline creates this agent through ``build_decision_agent`` and
hands over only a bigint session id.  Approval continuation reuses the same
factory without rebuilding the Finance or Risk stages.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agents import Agent, ModelSettings, OpenAIChatCompletionsModel, Runner
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

from app.Agent.bus import event_bus
from app.Agent.hooks import AppContext, CustomAgentHooks
from app.Agent.prompt_loader import load_prompt
from app.Agent.state_store import (
    commit_initial_result,
    get_approval_state,
    initialize_approval_state,
)
from app.schema.decisionAgent import DecisionBatchOutput
from app.service.decision_guard import (
    apply_authoritative_precheck_state,
    validate_decision_prechecks,
)
from app.tools.DecisionAgent.GetBankProduct import list_bank_products
from app.tools.DecisionAgent.PrecheckAPI import (
    precheck_micro_credit,
    precheck_performance_bond,
    precheck_trade_finance,
)
from app.tools.pipeline import load_decision_context


PROMPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "decisionAgent.md"
AGENT_NAME = "Decision_Agent"
_STANDALONE_AGENT: Agent[AppContext] | None = None


def build_decision_agent(
    *,
    handoffs: Sequence[Any] = (),
) -> Agent[AppContext]:
    """Create a Decision Agent; handoffs are injected by the pipeline factory."""
    from app.Agent.config import OPENAI_MODEL, get_openai_client

    prompt = load_prompt(PROMPT_PATH)
    if handoffs:
        prompt = prompt_with_handoff_instructions(prompt)
    return Agent(
        name=AGENT_NAME,
        model=OpenAIChatCompletionsModel(
            model=OPENAI_MODEL,
            openai_client=get_openai_client(),
        ),
        instructions=prompt,
        output_type=DecisionBatchOutput,
        tools=[
            load_decision_context,
            list_bank_products,
            precheck_performance_bond,
            precheck_trade_finance,
            precheck_micro_credit,
        ],
        handoffs=list(handoffs),
        model_settings=ModelSettings(parallel_tool_calls=False),
        hooks=CustomAgentHooks(AGENT_NAME),
    )


def get_decision_agent() -> Agent[AppContext]:
    global _STANDALONE_AGENT
    if _STANDALONE_AGENT is None:
        _STANDALONE_AGENT = build_decision_agent()
    return _STANDALONE_AGENT


async def run_decision_agent(
    user_input: str,
    *,
    context: AppContext | None = None,
    expected_contract_ids: list[str] | None = None,
    run_metadata: dict[str, object] | None = None,
    max_turns: int = 20,
):
    """Run Decision directly while preserving application-level HITL state."""
    if context is None:
        from app.database.context_store import (
            allocate_session_id,
            validate_pipeline_schema,
        )

        validate_pipeline_schema()
        session_id = allocate_session_id()
        context = AppContext(
            document_id=str(session_id),
            original_input=user_input,
            run_id=session_id,
        )
    else:
        session_id = context.run_id
        context.original_input = user_input

    agent = get_decision_agent()
    try:
        await initialize_approval_state(
            session_id,
            context,
            user_input,
            metadata=run_metadata,
        )
        result = await Runner.run(
            agent,
            input=user_input,
            context=context,
            max_turns=max_turns,
        )
        if result.interruptions:
            raise RuntimeError(
                "Unexpected SDK interruption: precheck tools use StateStore gating"
            )
        if not isinstance(result.final_output, DecisionBatchOutput):
            raise TypeError("Decision Agent did not return DecisionBatchOutput")

        returned_ids = [item.contract_id for item in result.final_output.decisions]
        if expected_contract_ids is not None and returned_ids != expected_contract_ids:
            raise RuntimeError(
                "Agent returned an incomplete or incorrectly ordered batch: "
                f"expected={expected_contract_ids}, returned={returned_ids}"
            )

        state_before_commit = await get_approval_state(session_id)
        decision_output = apply_authoritative_precheck_state(
            result.final_output,
            state_before_commit,
        )
        validate_decision_prechecks(decision_output, state_before_commit)
        decision_result = decision_output.model_dump(mode="json")
        state = await commit_initial_result(
            session_id,
            decision_result,
            result.to_input_list(mode="normalized"),
        )
        pending = [
            request
            for request in state["approval_requests"]
            if request["status"] == "pending"
        ]
        await event_bus.emit(
            session_id,
            {
                "type": "run_review" if pending else "run_finished",
                "agent": AGENT_NAME,
                "task": (
                    "Decision Cards complete; precheck approval is pending"
                    if pending
                    else "Decision batch complete"
                ),
                "status": "review" if pending else "done",
                "data": (
                    {
                        "decision_result": decision_result,
                        "pending_approvals": pending,
                    }
                    if pending
                    else decision_result
                ),
            },
        )
        return result
    except asyncio.CancelledError:
        await asyncio.shield(
            event_bus.emit(
                session_id,
                {
                    "type": "run_cancelled",
                    "agent": AGENT_NAME,
                    "task": "Decision Agent cancelled",
                    "status": "cancelled",
                },
            )
        )
        raise
    except Exception as exc:
        await event_bus.emit(
            session_id,
            {
                "type": "run_error",
                "agent": AGENT_NAME,
                "task": "Decision Agent failed",
                "status": "error",
                "data": {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
            },
        )
        raise
    finally:
        snapshot = event_bus.get_snapshot(session_id)
        if snapshot is not None:
            log_path = event_bus.persist_snapshot(session_id)
            print(f"Agent log saved to: {log_path}")
        try:
            if "decision_result" in locals():
                from app.tools.writeLogs import persist_agent_stage_log

                persist_agent_stage_log(session_id, "decision", decision_result)
        except Exception as exc:
            print(
                "[decision] Could not persist DecisionLogs: "
                f"{type(exc).__name__}: {exc}"
            )


__all__ = [
    "AGENT_NAME",
    "build_decision_agent",
    "get_decision_agent",
    "run_decision_agent",
]
