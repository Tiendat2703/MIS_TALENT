import asyncio
from collections.abc import Callable
from typing import Any

import requests
from agents import RunContextWrapper, function_tool

from app.Agent.bus import event_bus
from app.Agent.hooks import AppContext
from app.Agent.state_store import (
    claim_approval_execution,
    complete_approval_execution,
    fail_approval_execution,
    get_approval_state,
    register_approval_request,
)


def _call_api(
    base_url: str | None,
    endpoint: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Call a real bank endpoint and never synthesize a precheck response."""
    if not base_url:
        raise RuntimeError(
            f"Bank API base URL is not configured for endpoint {endpoint}"
        )

    response = requests.post(
        f"{base_url.rstrip('/')}{endpoint}",
        json=payload,
        timeout=5,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"Invalid response from bank API {endpoint}: expected object")
    return result


def _pending_response(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_id": request["approval_id"],
        "approval_state": request["status"],
        "approval_status": False,
        "eligible": None,
        "score": None,
        "note": None,
        "eligible_score": None,
        "precheck_note": None,
    }


async def _run_gated_precheck(
    context: RunContextWrapper[AppContext],
    *,
    contract_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Gate the external call by exact tool arguments stored for this run."""
    run_id = context.context.run_id

    # A continuation may execute only the exact invocation approved by a human.
    # Reject mismatches before registration so they cannot pollute StateStore or
    # accidentally become a second approval request.
    continuation_approval_id = context.context.continuation_approval_id
    if continuation_approval_id is not None:
        state = await get_approval_state(run_id)
        approved_request = next(
            (
                item
                for item in state["approval_requests"]
                if item["approval_id"] == continuation_approval_id
            ),
            None,
        )
        if approved_request is None:
            raise ValueError(
                f"Unknown continuation approval: {continuation_approval_id}"
            )
        if (
            approved_request["contract_id"] != contract_id
            or approved_request["tool"] != tool_name
            or approved_request["arguments"] != arguments
        ):
            raise PermissionError(
                "Tool invocation does not match the exact human-approved request"
            )

    request = await register_approval_request(
        run_id,
        contract_id,
        tool_name,
        arguments,
    )
    newly_registered = request.pop("_newly_registered", False)

    if request["status"] == "executed":
        return dict(request["result"])

    if request["status"] != "approved":
        # A deterministic reconciliation may already have registered and logged
        # this exact request. Do not emit a duplicate approval event.
        if not newly_registered:
            return _pending_response(request)
        await event_bus.emit(run_id, {
            "type": "approval_requested",
            "agent": "Decision_Agent",
            "task": f"Chờ phê duyệt {tool_name} cho {contract_id}",
            "status": "review",
            "data": {
                "approval_id": request["approval_id"],
                "contract_id": contract_id,
                "tool": tool_name,
                "arguments": arguments,
                "approval_state": request["status"],
            },
        })
        return _pending_response(request)

    claimed = await claim_approval_execution(run_id, request["approval_id"])
    if not claimed["claimed"]:
        if claimed["status"] == "executed":
            return dict(claimed["result"])
        return _pending_response(claimed)

    try:
        raw_result = await asyncio.to_thread(execute)

        score = raw_result.get("score")
        note = raw_result.get("note")
        if not isinstance(score, (int, float)) or not isinstance(note, str):
            raise ValueError(
                f"Invalid response from {tool_name}: score/note are required"
            )

        result = {
            "approval_id": request["approval_id"],
            "approval_state": "executed",
            "approval_status": True,
            "eligible": bool(raw_result.get("eli", score >= 70)),
            "score": float(score),
            "note": note,
            "eligible_score": float(score),
            "precheck_note": note,
        }
        await complete_approval_execution(
            run_id,
            request["approval_id"],
            result,
        )
        await event_bus.emit(run_id, {
            "type": "approval_executed",
            "agent": "Decision_Agent",
            "task": f"Đã thực thi {tool_name} cho {contract_id}",
            "status": "done",
            "data": result,
        })
        return result
    except Exception as exc:
        await fail_approval_execution(
            run_id,
            request["approval_id"],
            f"{type(exc).__name__}: {exc}",
        )
        raise


def _performance_bond_call(
    contract_id: str,
    amount: float,
) -> dict[str, Any]:
    _validate_performance_bond_arguments(contract_id, amount)

    # This integration is a local demo only. Return a deterministic result
    # without requiring a separately hosted VietinBank sandbox.
    if amount > 1_000_000_000:
        score = 60
        note = "Hồ sơ cần thẩm định thêm vì số tiền bảo lãnh cao."
    else:
        score = 85
        note = "Hồ sơ đầy đủ và đủ điều kiện sơ bộ."

    return {
        "eli": score >= 70,
        "score": score,
        "note": note,
    }


def _validate_performance_bond_arguments(
    contract_id: str,
    amount: float,
) -> None:
    if not isinstance(contract_id, str) or not contract_id.strip() or amount <= 0:
        raise ValueError(
            "Hồ sơ thiếu thông tin hợp đồng hoặc số tiền bảo lãnh hợp lệ."
        )


def _validate_trade_finance_arguments(
    contract_id: str,
    supplier_docs: list[str],
    amount: float,
) -> None:
    if not isinstance(contract_id, str) or not contract_id.strip() or amount <= 0:
        raise ValueError(
            "Hồ sơ thiếu thông tin hợp đồng hoặc số tiền đề nghị hợp lệ."
        )
    if not isinstance(supplier_docs, list):
        raise ValueError("supplier_docs phải là danh sách chứng từ")


def _validate_micro_credit_arguments(
    contract_id: str,
    amount: float,
    receivable_list: list[str],
) -> None:
    if (
        not isinstance(contract_id, str)
        or not contract_id.strip()
        or amount <= 0
    ):
        raise ValueError(
            "Hồ sơ thiếu hợp đồng hoặc số tiền vay hợp lệ."
        )
    if not isinstance(receivable_list, list):
        raise ValueError("receivable_list phải là danh sách khoản phải thu")


def _trade_finance_call(
    contract_id: str,
    supplier_docs: list[str],
    amount: float,
) -> dict[str, Any]:
    _validate_trade_finance_arguments(contract_id, supplier_docs, amount)

    # This integration is a local demo only. Return a deterministic result
    # without requiring a separately hosted VietinBank sandbox.
    if len(supplier_docs) < 2:
        score = 55
        note = "Hồ sơ chưa đủ chứng từ nhà cung cấp."
    else:
        score = 88
        note = "Hồ sơ đầy đủ và có thể chuyển sang bước thẩm định."

    return {
        "eli": score >= 70,
        "score": score,
        "note": note,
    }


def _micro_credit_call(
    contract_id: str,
    amount: float,
    receivable_list: list[str],
) -> dict[str, Any]:
    _validate_micro_credit_arguments(
        contract_id,
        amount,
        receivable_list,
    )

    # This integration is a local demo only. Keep the response deterministic so
    # approving a request does not require a separately hosted COOPBANK sandbox.
    if not receivable_list:
        score = 50
        note = "Hồ sơ chưa có danh sách khoản phải thu."
    elif amount > 300_000_000:
        score = 65
        note = "Hồ sơ cần thẩm định thêm vì số tiền vay cao."
    else:
        score = 82
        note = "Hồ sơ đạt điều kiện sơ bộ cho khoản vay vốn lưu động."

    return {
        "eli": score >= 70,
        "score": score,
        "note": note,
    }


@function_tool
async def precheck_performance_bond(
    context: RunContextWrapper[AppContext],
    contract_id: str,
    amount: float,
) -> dict:
    """Gate and run the deterministic mock performance-bond precheck."""
    _validate_performance_bond_arguments(contract_id, amount)
    arguments = {
        "contract_id": contract_id,
        "amount": amount,
    }
    return await _run_gated_precheck(
        context,
        contract_id=contract_id,
        tool_name="precheck_performance_bond",
        arguments=arguments,
        execute=lambda: _performance_bond_call(**arguments),
    )


@function_tool
async def precheck_trade_finance(
    context: RunContextWrapper[AppContext],
    contract_id: str,
    supplier_docs: list[str],
    amount: float,
) -> dict:
    """Gate and run the deterministic mock trade-finance precheck."""
    _validate_trade_finance_arguments(contract_id, supplier_docs, amount)
    arguments = {
        "contract_id": contract_id,
        "supplier_docs": supplier_docs,
        "amount": amount,
    }
    return await _run_gated_precheck(
        context,
        contract_id=contract_id,
        tool_name="precheck_trade_finance",
        arguments=arguments,
        execute=lambda: _trade_finance_call(**arguments),
    )


@function_tool
async def precheck_micro_credit(
    context: RunContextWrapper[AppContext],
    contract_id: str,
    amount: float,
    receivable_list: list[str],
) -> dict:
    """Gate and run the deterministic mock micro-credit precheck."""
    # Customer type is not part of this mock contract. The supplied receivables
    # and amount deterministically select the local demo response.
    _validate_micro_credit_arguments(
        contract_id,
        amount,
        receivable_list,
    )
    arguments = {
        "contract_id": contract_id,
        "amount": amount,
        "receivable_list": receivable_list,
    }
    return await _run_gated_precheck(
        context,
        contract_id=contract_id,
        tool_name="precheck_micro_credit",
        arguments=arguments,
        execute=lambda: _micro_credit_call(**arguments),
    )


PRECHECK_TOOLS = [
    precheck_performance_bond,
    precheck_trade_finance,
    precheck_micro_credit,
]

PRECHECK_TOOL_BY_NAME = {
    tool.name: tool
    for tool in PRECHECK_TOOLS
}
