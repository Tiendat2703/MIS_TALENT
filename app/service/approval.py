import asyncio
import json
import sys
import traceback
from dataclasses import asdict
from typing import Any

from agents import Runner

from app.Agent.bus import event_bus
from app.Agent.decisionAgent import DecisionAgent, run_decision_agent
from app.Agent.state_store import (
    commit_continuation_result,
    get_approval_state,
    list_approval_requests,
    load_context,
    load_conversation_items,
    set_approval_decision,
)
from app.tools.DecisionAgent.PrecheckAPI import PRECHECK_TOOL_BY_NAME


IMMUTABLE_TARGET_FIELDS = {
    "contract_id",
    "capital_need",
}


def _index_decisions(batch: dict[str, Any]) -> dict[str, dict[str, Any]]:
    decisions = batch.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("Decision output does not contain a valid decisions list")

    indexed: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("Every Decision Card must be an object")
        contract_id = decision.get("contract_id")
        if not isinstance(contract_id, str):
            raise ValueError("Decision Card is missing a valid contract_id")
        if contract_id in indexed:
            raise ValueError(f"Duplicate Decision Card for {contract_id}")
        indexed[contract_id] = decision
    return indexed


def _find_request(
    state: dict[str, Any],
    approval_id: str,
) -> dict[str, Any]:
    for request in state.get("approval_requests", []):
        if request.get("approval_id") == approval_id:
            return request
    raise KeyError(f"Approval request not found: {approval_id}")


def _guard_continuation_result(
    *,
    batch_before: dict[str, Any],
    batch_after: dict[str, Any],
    contract_id: str,
    approved: bool,
    approval_request: dict[str, Any],
    request_ids_before: set[str],
    request_ids_after: set[str],
) -> None:
    before = _index_decisions(batch_before)
    after = _index_decisions(batch_after)

    ids_before = [item["contract_id"] for item in batch_before["decisions"]]
    ids_after = [item["contract_id"] for item in batch_after["decisions"]]
    if ids_after != ids_before:
        raise ValueError(
            "Agent added, removed, duplicated, or reordered Decision Cards"
        )

    if request_ids_after != request_ids_before:
        raise ValueError(
            "Agent created an unapproved tool request during continuation"
        )

    if contract_id not in before or contract_id not in after:
        raise ValueError(f"Decision Card not found for {contract_id}")

    for cid, previous_decision in before.items():
        if cid != contract_id and after[cid] != previous_decision:
            raise ValueError(
                f"Agent modified Decision Card for unrelated contract {cid}"
            )

    target_before = before[contract_id]
    target_after = after[contract_id]
    for field in IMMUTABLE_TARGET_FIELDS:
        if target_after.get(field) != target_before.get(field):
            raise ValueError(
                f"Agent modified immutable field {contract_id}.{field}"
            )

    if approved:
        if approval_request.get("status") != "executed":
            raise ValueError(
                "Approved precheck was not executed successfully"
            )
        tool_result = approval_request.get("result")
        if not isinstance(tool_result, dict):
            raise ValueError("Executed precheck does not contain a result")
        if target_after.get("approval_status") is not True:
            raise ValueError("Agent did not set approval_status=true")
        if target_after.get("eligible_score") != tool_result.get("eligible_score"):
            raise ValueError("eligible_score does not match the precheck result")
        if target_after.get("precheck_note") != tool_result.get("precheck_note"):
            raise ValueError("precheck_note does not match the precheck result")
    else:
        if approval_request.get("status") != "rejected":
            raise ValueError("Rejected approval has an invalid StateStore status")
        if target_after.get("approval_status") is not False:
            raise ValueError("Rejected precheck must keep approval_status=false")
        if target_after.get("eligible_score") is not None:
            raise ValueError("Rejected precheck must keep eligible_score=null")
        if target_after.get("precheck_note") is not None:
            raise ValueError("Rejected precheck must keep precheck_note=null")


async def get_pending_approvals(run_id: str) -> list[dict[str, Any]]:
    requests = await list_approval_requests(run_id)
    return [request for request in requests if request["status"] == "pending"]


def _followup_message(
    request: dict[str, Any],
    approved: bool,
) -> dict[str, Any]:
    contract_id = request["contract_id"]
    if approved:
        instruction = (
            "Approval đã được ghi trong StateStore. Hãy gọi đúng tool với đúng "
            "arguments bên dưới. Sau khi nhận kết quả thật, hãy đánh giá lại "
            "approve/review/reject và chỉ cập nhật Decision Card của contract này. "
            "Mọi Decision Card khác phải được trả lại nguyên vẹn."
        )
    else:
        instruction = (
            "Người duyệt đã từ chối precheck. Không gọi bất kỳ tool nào. Chỉ cập "
            "nhật Decision Card của contract này với approval_status=false, "
            "eligible_score=null, precheck_note=null; giữ nguyên mọi card khác."
        )

    payload = {
        "type": "approval_continuation",
        "approval_id": request["approval_id"],
        "approved": approved,
        "contract_id": contract_id,
        "tool": request["tool"],
        "arguments": request["arguments"],
        "instruction": instruction,
    }
    return {
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False),
    }


async def decide_approval(
    run_id: str,
    approval_id: str,
    approved: bool,
) -> dict[str, Any]:
    """Continue the saved conversation and update exactly one Decision Card."""
    state_before = await get_approval_state(run_id)
    request_before = _find_request(state_before, approval_id)
    batch_before = state_before.get("decision_result")
    if not isinstance(batch_before, dict):
        raise ValueError(f"Run {run_id} has no saved Decision Batch")

    if request_before.get("decision_applied_at") is not None:
        was_approved = request_before["status"] == "executed"
        if approved != was_approved:
            raise ValueError(
                f"Approval {approval_id} was already applied as "
                f"{'accept' if was_approved else 'reject'}"
            )
        return batch_before

    previous_items = await load_conversation_items(run_id)
    _, context = await load_context(run_id)
    context.continuation_approval_id = approval_id if approved else None
    request_ids_before = {
        request["approval_id"]
        for request in state_before["approval_requests"]
    }

    request = await set_approval_decision(run_id, approval_id, approved)
    tool = PRECHECK_TOOL_BY_NAME.get(request["tool"])
    if approved and tool is None:
        raise ValueError(f"Unsupported approved tool: {request['tool']}")

    continuation_agent = DecisionAgent.clone(
        tools=[tool] if approved else [],
    )
    followup = _followup_message(request, approved)

    try:
        await event_bus.emit(run_id, {
            "type": "run_resumed",
            "agent": DecisionAgent.name,
            "task": f"Tiếp tục đánh giá {request['contract_id']} sau approval",
            "status": "running",
            "data": {
                "approval_id": approval_id,
                "approved": approved,
                "contract_id": request["contract_id"],
            },
        })

        result = await Runner.run(
            continuation_agent,
            input=previous_items + [followup],
            context=context,
            max_turns=10,
        )
        if result.interruptions:
            raise RuntimeError("Unexpected SDK interruption during continuation")

        new_batch = asdict(result.final_output)
        state_after_tool = await get_approval_state(run_id)
        request_after = _find_request(state_after_tool, approval_id)
        request_ids_after = {
            item["approval_id"]
            for item in state_after_tool["approval_requests"]
        }

        _guard_continuation_result(
            batch_before=batch_before,
            batch_after=new_batch,
            contract_id=request["contract_id"],
            approved=approved,
            approval_request=request_after,
            request_ids_before=request_ids_before,
            request_ids_after=request_ids_after,
        )

        committed = await commit_continuation_result(
            run_id,
            expected_revision=state_after_tool["revision"],
            approval_id=approval_id,
            decision_result=new_batch,
            conversation_items=result.to_input_list(mode="normalized"),
        )
        await event_bus.emit(run_id, {
            "type": "decision_updated",
            "agent": DecisionAgent.name,
            "task": f"Đã cập nhật Decision Card cho {request['contract_id']}",
            "status": committed["workflow_status"],
            "data": new_batch,
        })
        return new_batch
    except asyncio.CancelledError:
        await asyncio.shield(event_bus.emit(run_id, {
            "type": "run_cancelled",
            "agent": DecisionAgent.name,
            "task": "Decision continuation bị dừng",
            "status": "cancelled",
            "data": {"approval_id": approval_id},
        }))
        raise
    except Exception as exc:
        await event_bus.emit(run_id, {
            "type": "decision_update_rejected",
            "agent": DecisionAgent.name,
            "task": "Từ chối commit continuation output",
            "status": "error",
            "data": {
                "approval_id": approval_id,
                "error_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        })
        raise
    finally:
        if event_bus.get_snapshot(run_id) is not None:
            log_path = event_bus.persist_snapshot(run_id)
            print(f"Agent log saved to: {log_path}")


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "accept", "approve"}:
        return True
    if normalized in {"false", "0", "no", "n", "reject", "deny"}:
        return False
    raise ValueError("Decision must be accept/approve/true or reject/false")


async def _start_demo_run() -> str:
    contract_id = "HITL-TEST-001"
    user_input = f"""
Đây là integration test cho application-level human approval.
Hãy gọi trực tiếp tool precheck_performance_bond với đúng các tham số sau:
- contract_id: {contract_id}
- amount: 420000000

Nếu tool trả pending, vẫn phải hoàn tất một Decision Card đầy đủ với
decision_status=review, approval_status=false, eligible_score=null và
precheck_note=null. Không hỏi thêm thông tin trong test này.
""".strip()

    result = await run_decision_agent(
        user_input,
        expected_contract_ids=[contract_id],
        run_metadata={"mode": "approval_demo", "contract_ids": [contract_id]},
    )
    run_id = result.context_wrapper.context.run_id
    print("\nINITIAL DECISION BATCH:")
    print(
        json.dumps(
            asdict(result.final_output),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    print(f"\nDemo run completed in review state. run_id={run_id}")
    return run_id


async def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1].lower() == "demo":
        run_id = await _start_demo_run()
        pending = await get_pending_approvals(run_id)
        print("\nPENDING TOOLS:")
        print(json.dumps(pending, ensure_ascii=False, indent=2, default=str))
        print("\nContinue with one exact approval_id:")
        for request in pending:
            print(
                "  python3 -m app.service.approval "
                f"{run_id} {request['approval_id']} accept"
            )
            print(
                "  python3 -m app.service.approval "
                f"{run_id} {request['approval_id']} reject"
            )
        return

    if len(sys.argv) != 4:
        print("Usage:")
        print("  python3 -m app.service.approval demo")
        print(
            "  python3 -m app.service.approval "
            "<run_id> <approval_id> <accept|reject>"
        )
        return

    run_id, approval_id, decision = sys.argv[1], sys.argv[2], sys.argv[3]
    approved = _parse_bool(decision)
    try:
        state = await get_approval_state(run_id)
        request = _find_request(state, approval_id)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"Cannot load approval: {exc}")
        return

    print(f"\nRUN ID: {run_id}")
    print(f"APPROVAL ID: {approval_id}")
    print(f"CONTRACT: {request['contract_id']}")
    print(f"TOOL: {request['tool']}")
    print(f"DECISION: {'APPROVE' if approved else 'REJECT'}")

    try:
        updated_batch = await decide_approval(run_id, approval_id, approved)
    except (FileNotFoundError, KeyError, PermissionError, RuntimeError, ValueError) as exc:
        print(f"Approval continuation failed: {exc}")
        return
    print("\nUPDATED DECISION BATCH:")
    print(
        json.dumps(
            updated_batch,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
