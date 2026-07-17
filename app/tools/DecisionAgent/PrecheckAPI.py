import asyncio
import os
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


def _response(score: int, note: str) -> dict[str, Any]:
    return {
        "eli": score >= 70,
        "score": score,
        "note": note,
    }


def _call_api(
    base_url: str | None,
    endpoint: str,
    payload: dict[str, Any],
    mock_response: dict[str, Any],
) -> dict[str, Any]:
    try:
        if not base_url:
            raise ValueError("API base URL is not configured")

        response = requests.post(
            f"{base_url.rstrip('/')}{endpoint}",
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return mock_response


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
    execute: Callable[[bool], dict[str, Any]],
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

    if request["status"] == "executed":
        return dict(request["result"])

    if request["status"] != "approved":
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
        state = await get_approval_state(run_id)
        force_mock = state.get("metadata", {}).get("mode") == "approval_demo"
        raw_result = await asyncio.to_thread(execute, force_mock)

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
    *,
    force_mock: bool,
) -> dict[str, Any]:
    if not contract_id or amount <= 0:
        mock_response = _response(
            40,
            "Hồ sơ thiếu thông tin hợp đồng hoặc số tiền bảo lãnh.",
        )
    elif amount > 1_000_000_000:
        mock_response = _response(
            60,
            "Hồ sơ cần thẩm định thêm vì số tiền bảo lãnh cao.",
        )
    else:
        mock_response = _response(85, "Hồ sơ đầy đủ và đủ điều kiện sơ bộ.")

    return _call_api(
        None if force_mock else os.getenv("VIETINBANK_API_BASE_URL"),
        "/openapi/v1/guarantee/precheck",
        {
            "contract_id": contract_id,
            "amount": amount,
        },
        mock_response,
    )


def _trade_finance_call(
    contract_id: str,
    supplier_docs: list[str],
    amount: float,
    *,
    force_mock: bool,
) -> dict[str, Any]:
    if not contract_id or amount <= 0:
        mock_response = _response(
            40,
            "Hồ sơ thiếu thông tin hợp đồng hoặc số tiền đề nghị.",
        )
    elif len(supplier_docs) < 2:
        mock_response = _response(55, "Hồ sơ chưa đủ chứng từ nhà cung cấp.")
    else:
        mock_response = _response(
            88,
            "Hồ sơ đầy đủ và có thể chuyển sang bước thẩm định.",
        )

    return _call_api(
        None if force_mock else os.getenv("VIETINBANK_API_BASE_URL"),
        "/openapi/v1/trade-finance/precheck",
        {
            "contract_id": contract_id,
            "supplier_docs": supplier_docs,
            "amount": amount,
        },
        mock_response,
    )


def _micro_credit_call(
    contract_id: str,
    customer_type: str,
    amount: float,
    receivable_list: list[str],
    *,
    force_mock: bool,
) -> dict[str, Any]:
    if not contract_id or not customer_type or amount <= 0:
        mock_response = _response(
            40,
            "Hồ sơ thiếu hợp đồng, loại khách hàng hoặc số tiền vay.",
        )
    elif not receivable_list:
        mock_response = _response(50, "Hồ sơ chưa có danh sách khoản phải thu.")
    elif amount > 300_000_000:
        mock_response = _response(
            65,
            "Hồ sơ cần thẩm định thêm vì số tiền vay cao.",
        )
    else:
        mock_response = _response(
            82,
            "Hồ sơ đạt điều kiện sơ bộ cho khoản vay vốn lưu động.",
        )

    return _call_api(
        None if force_mock else os.getenv("COOPBANK_API_BASE_URL"),
        "/sandbox/v1/micro-credit/precheck",
        {
            "contract_id": contract_id,
            "customer_type": customer_type,
            "amount": amount,
            "receivable_list": receivable_list,
        },
        mock_response,
    )


@function_tool
async def precheck_performance_bond(
    context: RunContextWrapper[AppContext],
    contract_id: str,
    amount: float,
) -> dict:
    """Gate and run the performance-bond precheck for one contract."""
    arguments = {
        "contract_id": contract_id,
        "amount": amount,
    }
    return await _run_gated_precheck(
        context,
        contract_id=contract_id,
        tool_name="precheck_performance_bond",
        arguments=arguments,
        execute=lambda force_mock: _performance_bond_call(
            **arguments,
            force_mock=force_mock,
        ),
    )


@function_tool
async def precheck_trade_finance(
    context: RunContextWrapper[AppContext],
    contract_id: str,
    supplier_docs: list[str],
    amount: float,
) -> dict:
    """Gate and run the trade-finance precheck for one contract."""
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
        execute=lambda force_mock: _trade_finance_call(
            **arguments,
            force_mock=force_mock,
        ),
    )


@function_tool
async def precheck_micro_credit(
    context: RunContextWrapper[AppContext],
    contract_id: str,
    customer_type: str,
    amount: float,
    receivable_list: list[str],
) -> dict:
    """Gate and run the micro-credit precheck for one contract."""
    arguments = {
        "contract_id": contract_id,
        "customer_type": customer_type,
        "amount": amount,
        "receivable_list": receivable_list,
    }
    return await _run_gated_precheck(
        context,
        contract_id=contract_id,
        tool_name="precheck_micro_credit",
        arguments=arguments,
        execute=lambda force_mock: _micro_credit_call(
            **arguments,
            force_mock=force_mock,
        ),
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
