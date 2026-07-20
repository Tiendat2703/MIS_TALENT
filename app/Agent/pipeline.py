"""Finance → Risk → Decision orchestrator using real Agents SDK handoffs."""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import date
from pathlib import Path
from typing import Any

from agents import RunContextWrapper, Runner, handoff
from pydantic import Field

from app.Agent.bus import event_bus
from app.Agent.decisionAgent import build_decision_agent
from app.Agent.financeAgent import build_finance_agent
from app.Agent.hooks import AppContext
from app.Agent.risk_compliance_agent import build_risk_agent
from app.Agent.state_store import (
    commit_initial_result,
    get_approval_state,
    initialize_approval_state,
)
from app.database.context_store import (
    PipelineContextRecord,
    allocate_session_id,
    load_pipeline_context,
    save_decision_pack,
    validate_pipeline_schema,
)
from app.schema.decisionAgent import DecisionBatchOutput, DecisionCardOutput
from app.schema.handoff_packs import PipelineHandoff, StrictModel
from app.schema.pipeline_input import ContractUploadPackage
from app.service.decision_guard import (
    validate_decision_finance_consistency,
    validate_decision_prechecks,
    validate_decision_risk_policy,
)
from app.service.credit_profile import load_contract_credit_profiles
from app.service.precheck_approval import ensure_precheck_approval_requests
from app.service.pipeline_input import load_contract_package, select_pipeline_scope
from app.tools.FinanceAgent.data_request import apply_form_submission
from app.tools.FinanceAgent.finance_data import load_all
from app.tools.writeLogs import persist_agent_stage_log


class PipelineRunResult(StrictModel):
    """Public pipeline result plus an internal, non-serialized context record."""

    session_id: int = Field(gt=0)
    decisions: list[DecisionCardOutput] = Field(min_length=1)
    pending_approvals: list[dict[str, Any]] = Field(default_factory=list)
    context: PipelineContextRecord = Field(exclude=True)


def _validate_identity(
    context: RunContextWrapper[AppContext],
    payload: PipelineHandoff,
) -> None:
    if payload.session_id != context.context.run_id:
        raise PermissionError(
            "Handoff payload attempted to switch to a different pipeline session"
        )


async def _accept_risk_handoff(
    context: RunContextWrapper[AppContext],
    payload: PipelineHandoff,
) -> None:
    _validate_identity(context, payload)
    record = await asyncio.to_thread(load_pipeline_context, payload.session_id)
    if record.finance_pack.contract_ids != context.context.contract_ids:
        raise PermissionError("Finance handoff contracts do not match AppContext")


async def _accept_decision_handoff(
    context: RunContextWrapper[AppContext],
    payload: PipelineHandoff,
) -> None:
    _validate_identity(context, payload)
    record = await asyncio.to_thread(load_pipeline_context, payload.session_id)
    if record.risk_pack is None:
        raise RuntimeError("Risk Agent handed off before risk_pack was persisted")
    if record.risk_pack.contract_ids != context.context.contract_ids:
        raise PermissionError("Risk handoff contracts do not match AppContext")


def build_pipeline_agents():
    """Wire all three agents in reverse order without module-level cycles."""
    decision_agent = build_decision_agent()
    to_decision = handoff(
        agent=decision_agent,
        input_type=PipelineHandoff,
        on_handoff=_accept_decision_handoff,
        tool_description_override=(
            "Transfer to Decision only after RiskPack is persisted. Payload must "
            "contain exactly the existing bigint session_id."
        ),
    )
    risk_agent = build_risk_agent(handoffs=[to_decision])
    to_risk = handoff(
        agent=risk_agent,
        input_type=PipelineHandoff,
        on_handoff=_accept_risk_handoff,
        tool_description_override=(
            "Transfer to Risk only after FinanceBatchPack is persisted. Payload "
            "must contain exactly the existing bigint session_id."
        ),
    )
    finance_agent = build_finance_agent(handoffs=[to_risk])
    return finance_agent, risk_agent, decision_agent


def _persist_available_stage_logs(session_id: int) -> None:
    """Best-effort DB logging; local event snapshots remain authoritative on error."""
    snapshot = event_bus.get_snapshot(session_id) or {}
    outputs: dict[str, Any] = {}
    try:
        record = load_pipeline_context(session_id)
    except Exception as exc:
        print(
            f"[pipeline] Context unavailable for complete DB logs: "
            f"{type(exc).__name__}: {exc}"
        )
    else:
        outputs["finance"] = record.finance_pack
        if record.risk_pack is not None:
            outputs["risk"] = record.risk_pack
        if record.decision_pack is not None:
            outputs["decision"] = record.decision_pack

    names = {
        "finance": "Finance_Agent",
        "risk": "Risk_Agent",
        "decision": "Decision_Agent",
    }
    started_stages = {
        stage
        for stage, agent_name in names.items()
        if any(
            event.get("agent") == agent_name
            or event.get("target_agent") == agent_name
            for event in snapshot.get("events", [])
        )
    }
    for stage in sorted(started_stages | outputs.keys()):
        output = outputs.get(stage) or {
            "status": snapshot.get("status", "error"),
            "message": "Stage ended before its handoff pack was persisted.",
        }
        try:
            persist_agent_stage_log(session_id, stage, output)
        except Exception as exc:
            print(
                f"[pipeline] Could not persist {stage} log: "
                f"{type(exc).__name__}: {exc}"
            )


async def run_pipeline(
    contract: ContractUploadPackage | dict[str, Any] | str | Path | None = None,
    *,
    session_id: int | None = None,
    reference_date: date | None = None,
    submission: dict[str, Any] | None = None,
    max_turns: int = 35,
) -> PipelineRunResult:
    """Run one automatic batch over normal data or one uploaded contract.

    With no arguments, all contracts from the configured normal source are
    processed.  With ``input_package``, normal data is still loaded as portfolio
    context, the package is merged run-locally, and its contract is processed.
    There is deliberately no targeted ``contract_id`` mode: existing-source
    runs always evaluate the complete source batch.
    """
    # Validate an external contract before reserving a durable pipeline ID. The
    # contract is the complete upload API; normal portfolio context is loaded by
    # the application, not supplied by the caller.
    upload = (
        await asyncio.to_thread(load_contract_package, contract)
        if contract is not None
        else None
    )
    await asyncio.to_thread(validate_pipeline_schema)
    if session_id is None:
        session_id = await asyncio.to_thread(allocate_session_id)

    data = await asyncio.to_thread(load_all)
    data, contract_ids, mode = await asyncio.to_thread(
        select_pipeline_scope,
        data,
        upload,
    )

    request = {
        "session_id": session_id,
        "mode": mode,
        "contract_ids": contract_ids,
        "instruction": (
            "Run Finance once for the complete contract batch, persist a "
            "FinanceBatchPack, hand off to Risk by this session_id, then hand "
            "off to Decision by the same session_id."
        ),
    }
    user_input = json.dumps(request, ensure_ascii=False)
    context = AppContext(
        document_id=f"BATCH-{session_id}",
        original_input=user_input,
        run_id=session_id,
        contract_id=contract_ids[0] if len(contract_ids) == 1 else None,
        contract_ids=contract_ids,
        reference_date=reference_date.isoformat() if reference_date else None,
    )

    await initialize_approval_state(
        session_id,
        context,
        user_input,
        metadata={
            "mode": mode,
            "contract_ids": contract_ids,
            "uploaded_contract_id": (
                upload.contract_id if upload is not None else None
            ),
        },
    )

    if submission:
        apply_form_submission(data, submission)
    context.finance_store["data"] = data

    await event_bus.emit(
        session_id,
        {
            "type": "run_started",
            "agent": "Finance_Agent",
            "task": "Finance → Risk → Decision pipeline started",
            "status": "running",
            "data": {
                "session_id": session_id,
                "mode": mode,
                "contract_ids": contract_ids,
            },
        },
    )

    finance_agent, _, _ = build_pipeline_agents()
    try:
        result = await Runner.run(
            finance_agent,
            input=user_input,
            context=context,
            max_turns=max_turns,
        )
        if result.interruptions:
            raise RuntimeError("Pipeline received an unexpected SDK interruption")
        if not isinstance(result.final_output, DecisionBatchOutput):
            raise TypeError(
                "Pipeline did not finish at Decision_Agent with DecisionBatchOutput"
            )
        returned_ids = [item.contract_id for item in result.final_output.decisions]
        if returned_ids != contract_ids:
            raise ValueError(
                "Decision output must contain all pipeline contracts in order: "
                f"expected={contract_ids}, returned={returned_ids}"
            )

        authoritative_context = await asyncio.to_thread(
            load_pipeline_context, session_id
        )
        credit_profiles = await asyncio.to_thread(
            load_contract_credit_profiles,
            authoritative_context.finance_pack.contract_ids,
        )
        validate_decision_finance_consistency(
            result.final_output,
            authoritative_context.finance_pack,
            credit_profiles,
        )
        if authoritative_context.risk_pack is None:
            raise ValueError(
                f"RiskBatchPack is missing for session_id={session_id}"
            )
        validate_decision_risk_policy(
            result.final_output,
            authoritative_context.risk_pack,
        )
        # Register every actionable precheck deterministically. The external bank
        # call is still blocked until a human approves the exact stored arguments.
        await ensure_precheck_approval_requests(
            session_id,
            result.final_output,
            authoritative_context.finance_pack,
            credit_profiles,
        )
        state_before_commit = await get_approval_state(session_id)
        validate_decision_prechecks(result.final_output, state_before_commit)
        await asyncio.to_thread(save_decision_pack, session_id, result.final_output)
        decision_json = result.final_output.model_dump(mode="json")
        state = await commit_initial_result(
            session_id,
            decision_json,
            result.to_input_list(mode="normalized"),
        )
        pending = [
            item
            for item in state["approval_requests"]
            if item["status"] == "pending"
        ]
        await event_bus.emit(
            session_id,
            {
                "type": "run_review" if pending else "run_finished",
                "agent": "Decision_Agent",
                "task": (
                    "Pipeline complete; precheck approval is pending"
                    if pending
                    else "Pipeline complete"
                ),
                "status": "review" if pending else "done",
                "data": (
                    {
                        "decision_result": decision_json,
                        "pending_approvals": pending,
                    }
                    if pending
                    else decision_json
                ),
            },
        )
        record = await asyncio.to_thread(load_pipeline_context, session_id)
        return PipelineRunResult(
            session_id=session_id,
            decisions=result.final_output.decisions,
            pending_approvals=pending,
            context=record,
        )
    except asyncio.CancelledError:
        await asyncio.shield(
            event_bus.emit(
                session_id,
                {
                    "type": "run_cancelled",
                    "agent": "Pipeline",
                    "task": "Pipeline cancelled",
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
                "agent": "Pipeline",
                "task": "Pipeline failed",
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
        if event_bus.get_snapshot(session_id) is not None:
            path = event_bus.persist_snapshot(session_id)
            print(f"Agent log saved to: {path}")
        await asyncio.to_thread(_persist_available_stage_logs, session_id)


async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run Finance → Risk → Decision")
    parser.add_argument(
        "--input",
        dest="input_package",
        help=(
            "Path to one contract JSON object. Omit it to process every contract "
            "from the configured normal source."
        ),
    )
    parser.add_argument("--reference-date", help="ISO date used for overdue checks")
    parser.add_argument("--max-turns", type=int, default=35)
    args = parser.parse_args()
    output = await run_pipeline(
        contract=args.input_package,
        reference_date=(
            date.fromisoformat(args.reference_date) if args.reference_date else None
        ),
        max_turns=args.max_turns,
    )
    print(output.model_dump_json(indent=2))


__all__ = [
    "PipelineRunResult",
    "build_pipeline_agents",
    "run_pipeline",
]


if __name__ == "__main__":
    asyncio.run(_main())
