"""Application service wrapping the Finance → Risk → Decision pipeline for an API.

Framework-agnostic: KHÔNG import FastAPI/Flask. Mỗi hàm trả về dữ liệu JSON được
hoặc async-yield event sẵn sàng cho SSE, để một lớp HTTP mỏng (vd FastAPI) chỉ việc
gọi lại. Luồng API đề xuất:

    1. POST /runs                      -> start_pipeline_run(...)   trả session_id ngay
    2. GET  /runs/{id}/events (SSE)    -> stream_run_events(id)     dashboard xem tiến trình
    3. GET  /runs/{id}                 -> get_run_result(id)        snapshot + kết quả
    4. GET  /runs/{id}/approvals       -> list_pending_approvals(id)
    5. POST /runs/{id}/approvals/{aid} -> submit_approval(id, aid, approved)  founder duyệt

``start_pipeline_run`` cấp session_id TRƯỚC rồi chạy pipeline ở task nền, nên client
mở được SSE ngay từ event đầu tiên. State (event_bus, task registry) nằm in-memory
trong tiến trình — hợp với dashboard live một tiến trình; nếu scale nhiều worker thì
cần chuyển event_bus sang backend chia sẻ (Redis...).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from app.Agent.bus import event_bus
from app.Agent.pipeline import run_pipeline
from app.database.context_store import (
    allocate_session_id,
    count_pipeline_contexts,
    fetch_context_row,
    fetch_context_rows,
    validate_pipeline_schema,
)
from app.service.approval import decide_approval, get_pending_approvals

# Trạng thái snapshot được coi là ĐÃ KẾT THÚC (đóng SSE, task xong).
_TERMINAL_STATUSES = {"done", "completed", "error", "cancelled"}

# Task nền đang chạy pipeline, theo session_id — để tra cứu trạng thái/đợi kết quả.
_RUNS: dict[int, asyncio.Task] = {}


def _coerce_reference_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _run_status(session_id: int) -> str:
    snapshot = event_bus.get_snapshot(session_id)
    if snapshot is None:
        return "unknown"
    return str(snapshot.get("status", "unknown"))


async def start_pipeline_run(
    *,
    contract: dict[str, Any] | str | None = None,
    scenario: str | None = None,
    reference_date: str | date | None = None,
    submission: dict[str, Any] | None = None,
    max_turns: int = 35,
) -> dict[str, Any]:
    """Cấp session_id, chạy pipeline ở task nền, trả về ngay để client subscribe SSE.

    contract: object hợp đồng upload (dict) hoặc đường dẫn file JSON; None = chạy
    toàn bộ hợp đồng từ nguồn dữ liệu thường.
    """
    await asyncio.to_thread(validate_pipeline_schema)
    session_id = await asyncio.to_thread(allocate_session_id)
    reference = _coerce_reference_date(reference_date)

    async def _runner() -> Any:
        # run_pipeline tự phát event (kể cả run_error) nên ở đây chỉ cần chạy.
        return await run_pipeline(
            contract,
            session_id=session_id,
            reference_date=reference,
            scenario=scenario,
            submission=submission,
            max_turns=max_turns,
        )

    task = asyncio.create_task(_runner(), name=f"pipeline-{session_id}")
    _RUNS[session_id] = task
    task.add_done_callback(lambda finished: _on_run_done(session_id, finished))

    return {"session_id": session_id, "status": "running"}


def _on_run_done(session_id: int, task: asyncio.Task) -> None:
    # Đọc exception để không bị "Task exception was never retrieved"; lỗi thật đã được
    # run_pipeline emit thành event run_error cho dashboard.
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            print(f"[pipeline-service] run {session_id} failed: {type(exc).__name__}: {exc}")


async def run_pipeline_and_wait(
    *,
    contract: dict[str, Any] | str | None = None,
    scenario: str | None = None,
    reference_date: str | date | None = None,
    submission: dict[str, Any] | None = None,
    max_turns: int = 35,
) -> dict[str, Any]:
    """Chạy pipeline đồng bộ và trả kết quả cuối (dùng khi API muốn chờ luôn)."""
    started = await start_pipeline_run(
        contract=contract,
        scenario=scenario,
        reference_date=reference_date,
        submission=submission,
        max_turns=max_turns,
    )
    session_id = started["session_id"]
    result = await _RUNS[session_id]
    return {
        "session_id": session_id,
        "status": _run_status(session_id),
        "decisions": [card.model_dump(mode="json") for card in result.decisions],
        "pending_approvals": result.pending_approvals,
    }


async def stream_run_events(
    session_id: int,
    *,
    include_history: bool = True,
    poll_interval: float = 15.0,
) -> AsyncIterator[dict[str, Any]]:
    """Async generator các event của một run, sẵn sàng cho SSE.

    Phát lại lịch sử (catch-up) rồi stream event mới; tự đóng khi run chạm trạng thái
    kết thúc. Giữ mở qua trạng thái 'review'/'paused' để bao trọn cả bước founder duyệt
    (decide_approval phát tiếp event trên cùng session_id).
    """
    queue = event_bus.subscribe(session_id)
    max_seq = 0
    try:
        if include_history:
            snapshot = event_bus.get_snapshot(session_id)
            for event in (snapshot or {}).get("events", []):
                seq = int(event.get("seq", 0))
                max_seq = max(max_seq, seq)
                yield event
            if snapshot and str(snapshot.get("status")) in _TERMINAL_STATUSES:
                return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=poll_interval)
            except asyncio.TimeoutError:
                # Heartbeat để giữ kết nối SSE sống và cho client biết vẫn đang chờ.
                yield {"type": "heartbeat", "run_id": str(session_id),
                        "status": _run_status(session_id)}
                if _run_status(session_id) in _TERMINAL_STATUSES:
                    return
                continue

            if int(event.get("seq", 0)) <= max_seq:
                continue  # bỏ event đã phát trong lịch sử
            max_seq = int(event.get("seq", 0))
            yield event

            if _run_status(session_id) in _TERMINAL_STATUSES:
                return
    finally:
        event_bus.unsubscribe(session_id, queue)


def get_run_snapshot(session_id: int) -> dict[str, Any] | None:
    """Snapshot hiện tại (status, events, result) để polling hoặc reconnect."""
    return event_bus.get_snapshot(session_id)


async def get_run_result(session_id: int) -> dict[str, Any]:
    """Kết quả có thẩm quyền: finance/risk/decision pack từ bảng context + approval."""
    from app.database.context_store import load_pipeline_context

    payload: dict[str, Any] = {
        "session_id": session_id,
        "status": _run_status(session_id),
    }
    try:
        record = await asyncio.to_thread(load_pipeline_context, session_id)
    except LookupError:
        payload["found"] = False
        return payload

    payload["found"] = True
    payload["finance_pack"] = record.finance_pack.model_dump(mode="json")
    payload["risk_pack"] = (
        record.risk_pack.model_dump(mode="json") if record.risk_pack else None
    )
    payload["decision_pack"] = (
        record.decision_pack.model_dump(mode="json") if record.decision_pack else None
    )
    payload["pending_approvals"] = await get_pending_approvals(session_id)
    return payload


def _pack_list(pack: Any, item_key: str) -> list[dict[str, Any]]:
    """Bung một cột pack thành list dict, chịu cả 2 schema.

    - Batch mới: {"packs": [...]} hoặc {"decisions": [...]}.
    - Phẳng cũ: bản thân dict là 1 pack đơn (có contract_id).
    """
    if not isinstance(pack, dict):
        return []
    items = pack.get(item_key)
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if pack.get("contract_id"):  # pack phẳng cũ = 1 hợp đồng
        return [pack]
    return []


def _by_contract(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["contract_id"]: item for item in items if item.get("contract_id")}


def _summarize_context(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Bung một run (raw dict) thành các dòng THEO HỢP ĐỒNG cho dashboard.

    Đọc bằng .get() nên dùng chung được cho schema batch mới và pack phẳng cũ; nhờ
    vậy KHÔNG bỏ sót hợp đồng nào đã lưu trong context.
    """
    session_id = row["session_id"]
    finance_packs = _pack_list(row.get("finance_pack"), "packs")
    risk_by = _by_contract(_pack_list(row.get("risk_pack"), "packs"))
    decision_by = _by_contract(_pack_list(row.get("decision_pack"), "decisions"))

    rows: list[dict[str, Any]] = []
    for finance in finance_packs:
        contract_id = finance.get("contract_id")
        risk = risk_by.get(contract_id)
        decision = decision_by.get(contract_id)
        cash_impact = finance.get("cash_impact") or {}
        rows.append(
            {
                "session_id": session_id,
                "contract_id": contract_id,
                # Đã đi tới bước nào: finance -> risk -> decision.
                "stage": "decision" if decision else ("risk" if risk else "finance"),
                "generated_at": finance.get("generated_at"),
                "finance": {
                    "contract_name": finance.get("contract_name"),
                    "start_date": finance.get("start_date"),
                    "end_date": finance.get("end_date"),
                    "funding_need_type": finance.get("funding_need_type"),
                    "requested_amount": finance.get("requested_amount"),
                    "contract_value": finance.get("contract_value"),
                    "gross_margin": finance.get("gross_margin"),
                    "status": finance.get("status"),
                    "additional_funding_need": cash_impact.get("additional_funding_need"),
                    "worst_month_after": cash_impact.get("worst_month_after"),
                },
                "risk": (
                    {
                        "overall_risk_level": risk.get("overall_risk_level"),
                        "human_approval_required": risk.get("human_approval_required"),
                        "triggered_rule_ids": risk.get("triggered_rule_ids", []),
                    }
                    if risk
                    else None
                ),
                # List gọn: chỉ tổng quan. Decision Card đầy đủ (reasons + điều kiện
                # bảo vệ) lấy ở GET /runs/{id}/decision.
                "decision": (
                    {
                        "recommended_option": decision.get("recommended_option"),
                        "decision_status": decision.get("decision_status"),
                        "accept_opportunity": decision.get("accept_opportunity"),
                        "risk_level": decision.get("risk_level"),
                        "capital_need": decision.get("capital_need"),
                        "requires_founder_confirmation": decision.get(
                            "requires_founder_confirmation"
                        ),
                        "approval_status": decision.get("approval_status"),
                    }
                    if decision
                    else None
                ),
            }
        )
    return rows


def _latest_per_contract(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Giữ mỗi contract_id đúng 1 dòng = run mới nhất.

    rows đến từ record đã sắp session_id DESC nên lần gặp ĐẦU tiên của mỗi
    contract_id chính là run mới nhất.
    """
    seen: set[str] = set()
    latest: list[dict[str, Any]] = []
    for row in rows:
        contract_id = row["contract_id"]
        if contract_id in seen:
            continue
        seen.add(contract_id)
        latest.append(row)
    return latest


async def list_processed_contracts(
    limit: int = 100,
    offset: int = 0,
    latest_only: bool = True,
) -> dict[str, Any]:
    """Hợp đồng đã xử lí, phẳng theo hợp đồng, cho dashboard.

    latest_only=True (mặc định): mỗi hợp đồng chỉ hiện run mới nhất.
    latest_only=False: hiện toàn bộ lịch sử chạy (mỗi run một dòng).
    """
    rows = await asyncio.to_thread(fetch_context_rows, limit, offset)
    total_runs = await asyncio.to_thread(count_pipeline_contexts)
    contracts: list[dict[str, Any]] = []
    for row in rows:
        contracts.extend(_summarize_context(row))
    if latest_only:
        contracts = _latest_per_contract(contracts)
    return {
        "total_runs": total_runs,
        "returned_runs": len(rows),
        "count": len(contracts),
        "latest_only": latest_only,
        "limit": limit,
        "offset": offset,
        "contracts": contracts,
    }


async def list_contract_overviews(
    limit: int = 100,
    offset: int = 0,
    latest_only: bool = True,
) -> dict[str, Any]:
    """JSON gọn cho FE: tên hợp đồng, giá trị, ngày bắt đầu/kết thúc, giá trị đề xuất.

    latest_only=True (mặc định): mỗi hợp đồng chỉ hiện run mới nhất.
    """
    rows = await asyncio.to_thread(fetch_context_rows, limit, offset)
    total_runs = await asyncio.to_thread(count_pipeline_contexts)
    contracts: list[dict[str, Any]] = []
    for row in rows:
        decision_by = _by_contract(_pack_list(row.get("decision_pack"), "decisions"))
        for finance in _pack_list(row.get("finance_pack"), "packs"):
            decision = decision_by.get(finance.get("contract_id"))
            contracts.append(
                {
                    "session_id": row["session_id"],
                    "contract_id": finance.get("contract_id"),
                    "contract_name": finance.get("contract_name"),   # tên hợp đồng
                    "contract_value": finance.get("contract_value"),  # giá trị hợp đồng
                    "start_date": finance.get("start_date"),          # ngày bắt đầu
                    "end_date": finance.get("end_date"),              # ngày kết thúc
                    "requested_amount": finance.get("requested_amount"),  # giá trị đề xuất
                    # Giá trị đề xuất cuối theo quyết định (nếu Decision đã chạy).
                    "recommended_capital": (
                        decision.get("capital_need") if decision else None
                    ),
                }
            )
    if latest_only:
        contracts = _latest_per_contract(contracts)
    return {
        "total_runs": total_runs,
        "count": len(contracts),
        "latest_only": latest_only,
        "limit": limit,
        "offset": offset,
        "contracts": contracts,
    }


async def get_decision_cards(session_id: int) -> dict[str, Any]:
    """Decision Card ĐẦY ĐỦ (phương án + 3 lý do + điều kiện bảo vệ) theo run id.

    Dùng cho màn Decision Reveal. Trả nguyên các card, chịu cả 2 schema.
    """
    row = await asyncio.to_thread(fetch_context_row, session_id)
    if row is None:
        return {"session_id": session_id, "found": False, "decisions": []}
    decisions = _pack_list(row.get("decision_pack"), "decisions")
    return {
        "session_id": session_id,
        "found": True,
        "count": len(decisions),
        "decisions": decisions,
    }


async def list_pending_approvals(session_id: int) -> list[dict[str, Any]]:
    """Các precheck đang chờ nhà sáng lập xác nhận (điểm cần con người duyệt)."""
    return await get_pending_approvals(session_id)


async def submit_approval(
    session_id: int,
    approval_id: str,
    approved: bool,
) -> dict[str, Any]:
    """Nhà sáng lập duyệt/từ chối một precheck; chạy tiếp và trả Decision Batch mới."""
    updated_batch = await decide_approval(session_id, approval_id, approved)
    return {
        "session_id": session_id,
        "approval_id": approval_id,
        "approved": approved,
        "status": _run_status(session_id),
        "decision_result": updated_batch,
        "pending_approvals": await get_pending_approvals(session_id),
    }


__all__ = [
    "get_decision_cards",
    "get_run_result",
    "get_run_snapshot",
    "list_contract_overviews",
    "list_pending_approvals",
    "list_processed_contracts",
    "run_pipeline_and_wait",
    "start_pipeline_run",
    "stream_run_events",
    "submit_approval",
]
