"""Deterministic evidence collector for the Validate Agent.

Orchestrator gửi cho validator hai thứ: (1) run_log của agent vừa chạy và (2) output
pack đã persist. Tool này gom đúng hai thứ đó theo ``session_id`` + ``stage`` và kèm
theo *policy* của stage (bảng/tool được phép, nguồn bị cấm, các bước quy trình bắt
buộc, loại output hợp lệ) để validator chỉ việc đối chiếu — nó KHÔNG tự phán xử ở
đây, việc phán xử là của LLM validator dựa trên checklist.
"""

from __future__ import annotations

from typing import Any

from agents import RunContextWrapper, function_tool

from app.Agent.bus import event_bus
from app.Agent.hooks import AppContext
from app.database.context_store import fetch_context_row


# Ai sở hữu stage nào (để lọc event_bus và gán target cho challenge ticket).
STAGE_AGENT = {
    "finance": "Finance_Agent",
    "risk": "Risk_Agent",
    "decision": "Decision_Agent",
}

# Khóa cột pack trong bảng public.context tương ứng mỗi stage.
STAGE_PACK_KEY = {
    "finance": "finance_pack",
    "risk": "risk_pack",
    "decision": "decision_pack",
}

# Policy từng stage — nguồn để validator đối chiếu ở nhóm B (tool/data source),
# C (output schema) và D (authority boundary). Đây KHÔNG phải verdict, chỉ là chuẩn.
STAGE_POLICY: dict[str, dict[str, Any]] = {
    "finance": {
        "allowed_input_tables": [
            "04_CONTRACTS", "06_ORDERS", "07_INVOICES", "08_BANK_TXN",
            "09_CASHFLOW", "02_OPC_PROFILE", "03_CUSTOMERS", "05_SERVICES",
            "05_PRODUCTS",
        ],
        "allowed_tools": [
            "load_and_validate", "reconcile_bank", "liquidity_funding",
            "classify_invoice", "margin_analysis", "missing_data",
            "prepare_finance_handoff",
        ],
        "forbidden_tools": [
            "match_bank_product", "precheck_performance_bond",
            "precheck_trade_finance", "precheck_micro_credit",
            "load_decision_context", "process_risk_context",
        ],
        "required_process_steps": [
            "data_validation", "invoice_bank_reconciliation", "liquidity_analysis",
            "ar_analysis", "margin_analysis", "funding_need_estimation",
            "finance_feature_pack_generation",
        ],
        "expected_output": "FinanceBatchPack / Finance Feature Pack (chỉ SỐ LIỆU)",
        "forbidden_output": [
            "Final Decision Card", "accept/reject cuối cùng",
            "partner service submission", "phán đoán rủi ro / readiness",
        ],
    },
    "risk": {
        "allowed_input_tables": [
            "13_RISK_RULES", "08_BANK_TXN", "20_DATA_CLASS", "FinanceBatchPack",
        ],
        "allowed_tools": ["process_risk_context"],
        "forbidden_tools": [
            "match_bank_product", "precheck_performance_bond",
            "precheck_trade_finance", "precheck_micro_credit",
            "load_decision_context",
        ],
        # Risk chạy TẤT ĐỊNH trong một tool (process_risk_context → build_risk_pack_impl),
        # nên run_log thường KHÔNG có process_step con. Đánh giá dựa trên NỘI DUNG
        # RiskBatchPack, không dựa vào process_steps_observed.
        "evaluation_note": (
            "QC ở đây là QC TOOL + SCHEMA + KHÔNG VƯỢT QUYỀN. Không phạt Risk vì "
            "không tìm ra rủi ro: rule_evaluations rỗng finding, status "
            "NOT_TRIGGERED / INSUFFICIENT_EVIDENCE, hay alerts rỗng đều là kết quả "
            "HỢP LỆ khi hợp đồng không vi phạm. run_log rỗng process_step cũng bình "
            "thường vì Risk chạy tất định trong một tool."
        ),
        "expected_output": (
            "RiskBatchPack (rule_evaluations, triggered_rule_ids, risk score, "
            "alerts, human_review_required)"
        ),
        "forbidden_output": [
            "Final Decision Card", "chọn sản phẩm ngân hàng cuối cùng",
            "accept/reject hợp đồng",
        ],
    },
    "decision": {
        "allowed_input_tables": [
            "FinanceBatchPack", "RiskBatchPack", "10_CREDIT_PROFILE",
            "11_BANK_PRODUCTS", "12_API_CATALOG",
        ],
        "allowed_tools": [
            "load_decision_context", "match_bank_product",
            "precheck_performance_bond", "precheck_trade_finance",
            "precheck_micro_credit",
        ],
        # Precheck API chỉ được gọi SAU human approval — validator phải chặn nếu
        # gọi trước (BLOCK_FINAL_DECISION). Không có tool bị cấm tuyệt đối ở đây.
        "forbidden_tools": ["process_risk_context", "prepare_finance_handoff"],
        "human_approval_gated_tools": [
            "precheck_performance_bond", "precheck_trade_finance",
            "precheck_micro_credit",
        ],
        "required_process_steps": [
            "load_decision_context", "bank_product_matching",
            "precheck_evaluation", "decision_card_generation",
        ],
        "expected_output": (
            "DecisionBatchOutput (Decision Card: option, đúng 3 reasons, "
            "human confirmation point, recommended partner service)"
        ),
        "forbidden_output": [
            "tự phê duyệt (approval_status=true khi chưa có human approval)",
            "tự gửi hồ sơ ngân hàng",
        ],
    },
}


def _get_snapshot(session_id: int) -> dict[str, Any]:
    snapshot = event_bus.get_snapshot(session_id)
    if snapshot is None:
        # Stage có thể đã chạy ở tiến trình khác; khôi phục từ file log.
        event_bus.restore_snapshot(session_id)
        snapshot = event_bus.get_snapshot(session_id)
    return snapshot or {"events": []}


def _stage_events(snapshot: dict[str, Any], agent_name: str) -> list[dict[str, Any]]:
    return [
        event
        for event in snapshot.get("events", [])
        if event.get("agent") == agent_name or event.get("target_agent") == agent_name
    ]


def _derive_run_log(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Bóc tools_called / process_steps / handoffs / errors từ event thô."""
    tools_called: list[str] = []
    process_steps: list[str] = []
    handoffs: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    for event in events:
        etype = event.get("type")
        if etype == "tool_started":
            name = event.get("tool_name")
            if name and name not in tools_called:
                tools_called.append(name)
        elif etype in {"finance_step", "data_supplemented", "data_request_required"}:
            task = event.get("task")
            if task:
                process_steps.append(task)
        elif etype == "agent_handoff":
            handoffs.append(
                {
                    "from": event.get("agent", ""),
                    "to": event.get("target_agent", ""),
                }
            )
        elif etype in {"run_error", "decision_update_rejected"}:
            errors.append(event.get("data") or {"message": event.get("task")})
    return {
        "tools_called": tools_called,
        "process_steps_observed": process_steps,
        "handoffs": handoffs,
        "errors": errors,
        "event_count": len(events),
    }


def collect_stage_evidence(session_id: int, stage: str) -> dict[str, Any]:
    """Gom run_log + output_pack + policy cho một stage. Không phán xử."""
    if stage not in STAGE_AGENT:
        raise ValueError(f"Unknown validation stage: {stage!r}")

    agent_name = STAGE_AGENT[stage]
    row = fetch_context_row(session_id)
    if row is None:
        raise LookupError(f"Pipeline context not found: session_id={session_id}")

    output_pack = row.get(STAGE_PACK_KEY[stage])
    snapshot = _get_snapshot(session_id)
    events = _stage_events(snapshot, agent_name)

    return {
        "session_id": session_id,
        "stage": stage,
        "agent_under_review": agent_name,
        "policy": STAGE_POLICY[stage],
        "output_pack": output_pack,
        "output_pack_present": output_pack is not None,
        "run_log": _derive_run_log(events),
        "raw_events": events,
        "run_status": snapshot.get("status"),
    }


@function_tool
async def load_validation_evidence(
    context: RunContextWrapper[AppContext],
    session_id: int,
    stage: str,
) -> dict:
    """Load run_log + output_pack + policy cho stage đang QC (finance/risk/decision).

    ``stage`` phải là một trong "finance", "risk", "decision". Tool chỉ đọc; validator
    tự đối chiếu với checklist rồi trả verdict. Số liệu trong pack là bất khả xâm phạm —
    validator không được sửa.
    """
    import asyncio

    if session_id != context.context.run_id:
        raise PermissionError(
            "Validation session_id does not match the Runner application context"
        )
    return await asyncio.to_thread(collect_stage_evidence, session_id, stage)


__all__ = [
    "STAGE_POLICY",
    "collect_stage_evidence",
    "load_validation_evidence",
]
