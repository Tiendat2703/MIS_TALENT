"""Sequential Finance → Validate → Risk → Validate → Decision → Validate pipeline.

Khác với ``app.Agent.pipeline`` (chuỗi SDK handoff chạy một mạch), orchestrator này
chạy TỪNG stage rời rạc theo cùng một ``session_id`` và chèn Validate Agent làm CỔNG
sau mỗi stage:

    Finance ──▶ Validate(finance) ──PASS──▶ Risk ──▶ Validate(risk) ──PASS──▶
        Decision ──▶ Validate(decision) ──PASS──▶ Final Decision Dashboard

Nếu bất kỳ cổng nào không trả ``PASS``, pipeline dừng ngay tại đó, xuất challenge
ticket để agent trước giải trình / chạy lại, và KHÔNG chạy stage sau.

Chạy:
    python -m app.Agent.validated_pipeline
    python -m app.Agent.validated_pipeline --input <contract.json> --reference-date 2026-07-18
"""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from app.Agent.bus import event_bus
from app.Agent.financeAgent import build_finance_agent
from app.Agent.hooks import AppContext
from app.Agent.pipeline import _persist_available_stage_logs
from app.Agent.risk_compliance_agent import main as run_risk_stage
from app.Agent.validatorAgent import persist_validator_reports, validate_stage
from app.database.context_store import (
    allocate_session_id,
    load_pipeline_context,
    save_decision_pack,
    validate_pipeline_schema,
)
from app.schema.decisionAgent import DecisionCardOutput
from app.schema.handoff_packs import StrictModel
from app.schema.pipeline_input import ContractUploadPackage
from app.schema.validatorAgent import ChallengeTicket, Stage, ValidationReport
from app.service.pipeline_input import load_contract_package, select_pipeline_scope
from app.tools.FinanceAgent.data_request import apply_form_submission
from app.tools.FinanceAgent.finance_data import load_all


PipelineStatus = Literal[
    "COMPLETE",
    "BLOCKED_AT_FINANCE",
    "BLOCKED_AT_RISK",
    "BLOCKED_AT_DECISION",
]

_BLOCK_STATUS: dict[str, PipelineStatus] = {
    "finance": "BLOCKED_AT_FINANCE",
    "risk": "BLOCKED_AT_RISK",
    "decision": "BLOCKED_AT_DECISION",
}


class ValidatedPipelineResult(StrictModel):
    """Kết quả pipeline có QC. ``decisions`` chỉ có khi ``status == COMPLETE``."""

    session_id: int = Field(gt=0)
    status: PipelineStatus
    decisions: list[DecisionCardOutput] = Field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = Field(default_factory=list)
    validation_reports: list[ValidationReport] = Field(default_factory=list)
    challenge_tickets: list[ChallengeTicket] = Field(default_factory=list)


async def _gate(
    session_id: int,
    stage: Stage,
    context: AppContext,
    reports: list[ValidationReport],
) -> ValidationReport:
    """Chạy validator cho một stage, tích lũy + persist report, trả report."""
    report = await validate_stage(session_id, stage, context=context)
    reports.append(report)
    await asyncio.to_thread(persist_validator_reports, session_id, reports)
    return report


def _blocked_result(
    session_id: int,
    stage: Stage,
    reports: list[ValidationReport],
) -> ValidatedPipelineResult:
    return ValidatedPipelineResult(
        session_id=session_id,
        status=_BLOCK_STATUS[stage],
        validation_reports=list(reports),
        challenge_tickets=[
            ticket for report in reports for ticket in report.challenge_tickets
        ],
    )


async def _run_finance_stage(
    session_id: int,
    context: AppContext,
    contract_ids: list[str],
    max_turns: int,
) -> None:
    """Chạy Finance rời rạc: 6 tool tính toán + persist FinanceBatchPack, KHÔNG handoff."""
    from agents import Runner

    finance_input = json.dumps(
        {
            "session_id": session_id,
            "contract_ids": contract_ids,
            "instruction": (
                "Chạy đủ 6 tool tài chính cho toàn bộ contract batch rồi gọi "
                "prepare_finance_handoff đúng một lần với session_id và contract_ids "
                "theo đúng thứ tự để persist FinanceBatchPack. KHÔNG handoff sang agent "
                "khác; dừng sau khi tool trả persisted=true."
            ),
        },
        ensure_ascii=False,
    )
    finance_agent = build_finance_agent(include_handoff_tool=True)
    result = await Runner.run(
        finance_agent,
        input=finance_input,
        context=context,
        max_turns=max_turns,
    )
    if result.interruptions:
        raise RuntimeError("Finance stage received an unexpected SDK interruption")
    # Xác nhận FinanceBatchPack đã nằm trong context trước khi cho validator kiểm.
    record = await asyncio.to_thread(load_pipeline_context, session_id)
    if record.finance_pack.contract_ids != contract_ids:
        raise RuntimeError(
            "Finance stage did not persist a FinanceBatchPack for the batch"
        )


async def _run_decision_stage(
    session_id: int,
    context: AppContext,
    contract_ids: list[str],
    max_turns: int,
):
    """Chạy Decision rời rạc theo session_id và persist DecisionBatchOutput.

    Chạy INLINE (không dùng run_decision_agent) để KHÔNG phát event terminal
    run_finished/run_review ở đây — event terminal do CỔNG validator cuối phát, nhờ
    vậy SSE không đóng trước khi Validate(decision) chạy xong.
    """
    from agents import Runner

    from app.Agent.decisionAgent import build_decision_agent
    from app.Agent.state_store import commit_initial_result, get_approval_state
    from app.schema.decisionAgent import DecisionBatchOutput
    from app.service.decision_guard import validate_decision_prechecks

    decision_input = json.dumps(
        {
            "session_id": session_id,
            "instruction": (
                "Gọi load_decision_context đúng một lần với session_id này, đánh giá "
                "từng case độc lập và trả DecisionBatchOutput đủ mọi contract theo thứ tự."
            ),
        },
        ensure_ascii=False,
    )
    result = await Runner.run(
        build_decision_agent(),
        input=decision_input,
        context=context,
        max_turns=max_turns,
    )
    if result.interruptions:
        raise RuntimeError("Decision stage received an unexpected SDK interruption")
    if not isinstance(result.final_output, DecisionBatchOutput):
        raise TypeError("Decision stage did not return a DecisionBatchOutput")
    returned_ids = [item.contract_id for item in result.final_output.decisions]
    if returned_ids != contract_ids:
        raise ValueError(
            "Decision output must contain all pipeline contracts in order: "
            f"expected={contract_ids}, returned={returned_ids}"
        )

    state_before = await get_approval_state(session_id)
    validate_decision_prechecks(result.final_output, state_before)
    await asyncio.to_thread(save_decision_pack, session_id, result.final_output)
    decision_json = result.final_output.model_dump(mode="json")
    await commit_initial_result(
        session_id, decision_json, result.to_input_list(mode="normalized")
    )
    await event_bus.emit(
        session_id,
        {
            "type": "decision_ready",
            "agent": "Decision_Agent",
            "task": "Decision batch xong; chờ Validator kiểm trước khi chốt",
            "status": "running",
            "data": decision_json,
        },
    )
    return result.final_output


async def run_validated_pipeline(
    contract: ContractUploadPackage | dict[str, Any] | str | Path | None = None,
    *,
    session_id: int | None = None,
    reference_date: date | None = None,
    scenario: str | None = None,
    submission: dict[str, Any] | None = None,
    finance_max_turns: int = 16,
    decision_max_turns: int = 20,
) -> ValidatedPipelineResult:
    """Run the gated pipeline. Dừng tại cổng đầu tiên không PASS."""
    from app.Agent.state_store import get_approval_state, initialize_approval_state

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
        select_pipeline_scope, data, upload
    )

    user_input = json.dumps(
        {"session_id": session_id, "mode": mode, "contract_ids": contract_ids},
        ensure_ascii=False,
    )
    context = AppContext(
        document_id=f"BATCH-{session_id}",
        original_input=user_input,
        run_id=session_id,
        contract_id=contract_ids[0] if len(contract_ids) == 1 else None,
        contract_ids=contract_ids,
        reference_date=reference_date.isoformat() if reference_date else None,
        scenario=scenario,
    )
    await initialize_approval_state(
        session_id,
        context,
        user_input,
        metadata={"mode": mode, "contract_ids": contract_ids, "gated": True},
    )
    if submission:
        apply_form_submission(data, submission)
    context.finance_store["data"] = data

    reports: list[ValidationReport] = []
    await event_bus.emit(
        session_id,
        {
            "type": "run_started",
            "agent": "Finance_Agent",
            "task": "Gated pipeline: Finance → Validate → Risk → Validate → Decision",
            "status": "running",
            "data": {"session_id": session_id, "mode": mode, "contract_ids": contract_ids},
        },
    )

    try:
        # ---- Stage 1: Finance → Validate(finance) ----
        await _run_finance_stage(session_id, context, contract_ids, finance_max_turns)
        finance_report = await _gate(session_id, "finance", context, reports)
        if not finance_report.passed:
            return await _emit_blocked(session_id, "finance", reports)

        # ---- Stage 2: Risk → Validate(risk) ----
        await run_risk_stage(session_id)
        risk_report = await _gate(session_id, "risk", context, reports)
        if not risk_report.passed:
            return await _emit_blocked(session_id, "risk", reports)

        # ---- Stage 3: Decision → Validate(decision) ----
        decision_output = await _run_decision_stage(
            session_id, context, contract_ids, decision_max_turns
        )
        decision_report = await _gate(session_id, "decision", context, reports)
        if not decision_report.passed:
            return await _emit_blocked(session_id, "decision", reports)

        # ---- Tất cả cổng PASS → Final Decision Dashboard ----
        state = await get_approval_state(session_id)
        pending = [
            item
            for item in state["approval_requests"]
            if item["status"] == "pending"
        ]
        await event_bus.emit(
            session_id,
            {
                "type": "run_review" if pending else "run_finished",
                "agent": "Validator_Agent",
                "task": (
                    "Pipeline PASS mọi cổng; precheck approval đang chờ"
                    if pending
                    else "Pipeline PASS mọi cổng QC — hoàn tất"
                ),
                "status": "review" if pending else "done",
                "data": {
                    "decision_result": decision_output.model_dump(mode="json"),
                    "pending_approvals": pending,
                    "validation_reports": [r.model_dump(mode="json") for r in reports],
                },
            },
        )
        return ValidatedPipelineResult(
            session_id=session_id,
            status="COMPLETE",
            decisions=decision_output.decisions,
            pending_approvals=pending,
            validation_reports=reports,
        )
    except asyncio.CancelledError:
        await asyncio.shield(
            event_bus.emit(
                session_id,
                {
                    "type": "run_cancelled",
                    "agent": "Pipeline",
                    "task": "Gated pipeline cancelled",
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
                "task": "Gated pipeline failed",
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


async def _emit_blocked(
    session_id: int,
    stage: Stage,
    reports: list[ValidationReport],
) -> ValidatedPipelineResult:
    result = _blocked_result(session_id, stage, reports)
    tickets = [t.model_dump(mode="json") for t in result.challenge_tickets]
    await event_bus.emit(
        session_id,
        {
            "type": "run_review",
            "agent": "Validator_Agent",
            "target_agent": {
                "finance": "Finance_Agent",
                "risk": "Risk_Agent",
                "decision": "Decision_Agent",
            }[stage],
            "task": f"CHẶN tại {stage}: {reports[-1].verdict} ({len(tickets)} ticket)",
            "status": "review",
            "data": {
                "blocked_stage": stage,
                "verdict": reports[-1].verdict,
                "challenge_tickets": tickets,
                "validation_reports": [r.model_dump(mode="json") for r in reports],
            },
        },
    )
    return result


async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run gated Finance → Validate → Risk → Validate → Decision"
    )
    parser.add_argument("--input", dest="input_package", help="Path to one contract JSON")
    parser.add_argument("--scenario", help="Optional normal-source override JSON")
    parser.add_argument("--reference-date", help="ISO date for overdue checks")
    args = parser.parse_args()
    result = await run_validated_pipeline(
        contract=args.input_package,
        scenario=args.scenario,
        reference_date=(
            date.fromisoformat(args.reference_date) if args.reference_date else None
        ),
    )
    print(result.model_dump_json(indent=2))


__all__ = [
    "ValidatedPipelineResult",
    "run_validated_pipeline",
]


if __name__ == "__main__":
    asyncio.run(_main())
