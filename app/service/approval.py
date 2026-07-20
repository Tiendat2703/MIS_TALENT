import asyncio
import hashlib
import json
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from agents import Runner

from app.Agent.bus import event_bus
from app.Agent.decisionAgent import get_decision_agent
from app.Agent.state_store import (
    commit_continuation_result,
    get_approval_state,
    list_approval_requests,
    load_context,
    load_conversation_items,
    restore_approval_state,
    set_approval_decision,
)
from app.Agent.hooks import AppContext
from app.database.context_store import fetch_context_row
from app.tools.DecisionAgent.PrecheckAPI import PRECHECK_TOOL_BY_NAME
from app.tools.writeLogs import fetch_decision_log


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


async def get_pending_approvals(run_id: int) -> list[dict[str, Any]]:
    try:
        requests = await list_approval_requests(run_id)
    except FileNotFoundError:
        decision_log = await asyncio.to_thread(fetch_decision_log, run_id)
        requests = _approval_requests_from_log(decision_log)
    return [request for request in requests if request["status"] == "pending"]


def _approval_requests_from_log(
    decision_log: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Recover exact approval requests from durable DecisionLogs."""
    if not decision_log:
        return []

    durable_state = decision_log.get("approval_state")
    if isinstance(durable_state, dict):
        requests = durable_state.get("approval_requests")
        if isinstance(requests, list):
            return [
                request
                for item in requests
                if isinstance(item, dict)
                and (request := _normalize_recovered_request(item)) is not None
            ]

    events = (decision_log.get("agent_log") or {}).get("events") or []
    for event in reversed(events):
        if not isinstance(event, dict) or event.get("type") != "run_review":
            continue
        pending = (event.get("data") or {}).get("pending_approvals")
        if isinstance(pending, list):
            return [
                request
                for item in pending
                if isinstance(item, dict)
                and (request := _normalize_recovered_request(item)) is not None
            ]

    recovered: dict[str, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "approval_requested":
            continue
        data = event.get("data") or {}
        approval_id = data.get("approval_id")
        contract_id = data.get("contract_id")
        tool = data.get("tool")
        arguments = data.get("arguments")
        if not all(isinstance(value, str) and value for value in (
            approval_id,
            contract_id,
            tool,
        )) or not isinstance(arguments, dict):
            continue
        request = _normalize_recovered_request({
            "approval_id": approval_id,
            "contract_id": contract_id,
            "tool": tool,
            "arguments": arguments,
            "status": data.get("approval_state", "pending"),
            "requested_at": event.get("ts"),
            "decided_at": None,
            "execution_started_at": None,
            "executed_at": None,
            "decision_applied_at": None,
            "result": None,
            "error": None,
        })
        if request is not None:
            recovered[approval_id] = request
    return list(recovered.values())


def _normalize_recovered_request(
    request: dict[str, Any],
) -> dict[str, Any] | None:
    approval_id = request.get("approval_id")
    contract_id = request.get("contract_id")
    tool = request.get("tool")
    arguments = request.get("arguments")
    if not all(isinstance(value, str) and value for value in (
        approval_id,
        contract_id,
        tool,
    )) or not isinstance(arguments, dict):
        return None

    normalized = dict(request)
    normalized.setdefault(
        "fingerprint",
        hashlib.sha256(
            json.dumps(
                {
                    "contract_id": contract_id,
                    "tool": tool,
                    "arguments": arguments,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )
    normalized.setdefault("status", "pending")
    normalized.setdefault("requested_at", None)
    normalized.setdefault("decided_at", None)
    normalized.setdefault("execution_started_at", None)
    normalized.setdefault("executed_at", None)
    normalized.setdefault("decision_applied_at", None)
    normalized.setdefault("result", None)
    normalized.setdefault("error", None)
    return normalized


async def _ensure_approval_state(run_id: int) -> dict[str, Any]:
    try:
        return await get_approval_state(run_id)
    except FileNotFoundError:
        pass

    decision_log = await asyncio.to_thread(fetch_decision_log, run_id)
    if not decision_log:
        raise FileNotFoundError(f"No durable approval state found for run_id={run_id}")

    durable_state = decision_log.get("approval_state")
    if isinstance(durable_state, dict):
        return await restore_approval_state(run_id, durable_state)

    requests = _approval_requests_from_log(decision_log)
    row = await asyncio.to_thread(fetch_context_row, run_id)
    if row is None:
        raise LookupError(f"Pipeline context not found: session_id={run_id}")

    finance_pack = row.get("finance_pack") or {}
    contract_ids = list(finance_pack.get("contract_ids") or [])
    if not contract_ids:
        contract_ids = [
            item.get("contract_id")
            for item in finance_pack.get("packs", [])
            if isinstance(item, dict) and item.get("contract_id")
        ]
    decision_result = decision_log.get("response") or row.get("decision_pack")
    if not isinstance(decision_result, dict):
        raise ValueError(f"Run {run_id} has no durable Decision Batch")

    original_input = json.dumps(
        {
            "session_id": run_id,
            "contract_ids": contract_ids,
            "instruction": "Recover persisted Decision approval state.",
        },
        ensure_ascii=False,
    )
    context = AppContext(
        document_id=f"BATCH-{run_id}",
        original_input=original_input,
        run_id=run_id,
        contract_id=contract_ids[0] if len(contract_ids) == 1 else None,
        contract_ids=contract_ids,
    )
    now = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "version": 2,
        "revision": 0,
        "run_id": run_id,
        "created_at": now,
        "updated_at": now,
        "workflow_status": "review",
        "context": asdict(context),
        "user_input": original_input,
        "metadata": {"mode": "recovered", "contract_ids": contract_ids},
        "approval_requests": requests,
        "decision_result": decision_result,
        "conversation_items": [],
    }
    return await restore_approval_state(run_id, snapshot)


def _followup_message(
    request: dict[str, Any],
    approved: bool,
    run_id: int,
    decision_batch_before: dict[str, Any],
) -> dict[str, Any]:
    contract_id = request["contract_id"]
    if approved:
        instruction = (
            "Approval đã được ghi trong StateStore. Hãy gọi đúng tool với đúng "
            "arguments bên dưới. Sau khi nhận kết quả thật, hãy đánh giá lại "
            "approve/review/reject và chỉ cập nhật Decision Card của contract này. "
            "Mọi Decision Card khác phải được trả lại nguyên vẹn. Sau khi cập nhật "
            "batch. Tầng ứng dụng sẽ tự lưu log."
        )
    else:
        instruction = (
            "Người duyệt đã từ chối precheck. Không gọi bất kỳ precheck tool nào. Chỉ cập "
            "nhật Decision Card của contract này với approval_status=false, "
            "eligible_score=null, precheck_note=null; giữ nguyên mọi card khác. "
            "Tầng ứng dụng sẽ tự lưu log sau khi batch được kiểm tra."
        )

    payload = {
        "type": "approval_continuation",
        "run_id": run_id,
        "approval_id": request["approval_id"],
        "approved": approved,
        "contract_id": contract_id,
        "tool": request["tool"],
        "arguments": request["arguments"],
        "decision_batch_before": decision_batch_before,
        "instruction": instruction,
    }
    return {
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False),
    }


async def decide_approval(
    run_id: int,
    approval_id: str,
    approved: bool,
) -> dict[str, Any]:
    """Continue the saved conversation and update exactly one Decision Card."""
    state_before = await _ensure_approval_state(run_id)
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

    decision_agent = get_decision_agent()
    continuation_agent = decision_agent.clone(
        tools=[tool] if approved else [],
    )
    followup = _followup_message(request, approved, run_id, batch_before)

    try:
        await event_bus.emit(run_id, {
            "type": "run_resumed",
            "agent": decision_agent.name,
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

        new_batch = result.final_output.model_dump(mode="json")
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

        try:
            from app.database.context_store import save_decision_pack

            await asyncio.to_thread(save_decision_pack, run_id, result.final_output)
        except LookupError:
            # Older standalone runs may not have a persisted Finance/Risk row.
            pass
        committed = await commit_continuation_result(
            run_id,
            expected_revision=state_after_tool["revision"],
            approval_id=approval_id,
            decision_result=new_batch,
            conversation_items=result.to_input_list(mode="normalized"),
        )
        await event_bus.emit(run_id, {
            "type": "decision_updated",
            "agent": decision_agent.name,
            "task": f"Đã cập nhật Decision Card cho {request['contract_id']}",
            "status": committed["workflow_status"],
            "data": new_batch,
        })
        return new_batch
    except asyncio.CancelledError:
        await asyncio.shield(event_bus.emit(run_id, {
            "type": "run_cancelled",
            "agent": decision_agent.name,
            "task": "Decision continuation bị dừng",
            "status": "cancelled",
            "data": {"approval_id": approval_id},
        }))
        raise
    except Exception as exc:
        await event_bus.emit(run_id, {
            "type": "decision_update_rejected",
            "agent": decision_agent.name,
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
        if "new_batch" in locals():
            try:
                from app.tools.writeLogs import persist_agent_stage_log

                await asyncio.to_thread(
                    persist_agent_stage_log,
                    run_id,
                    "decision",
                    new_batch,
                )
            except Exception as exc:
                print(
                    "Could not persist DecisionLogs: "
                    f"{type(exc).__name__}: {exc}"
                )


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y", "accept", "approve"}:
        return True
    if normalized in {"false", "0", "no", "n", "reject", "deny"}:
        return False
    raise ValueError("Decision must be accept/approve/true or reject/false")


async def main() -> None:
    if len(sys.argv) != 4:
        print("Usage:")
        print(
            "  python3 -m app.service.approval "
            "<run_id> <approval_id> <accept|reject>"
        )
        return

    try:
        run_id = int(sys.argv[1])
        if run_id <= 0:
            raise ValueError
    except ValueError:
        print("run_id must be a positive bigint session id")
        return
    approval_id, decision = sys.argv[2], sys.argv[3]
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
