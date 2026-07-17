"""Finance Agent tools — bản @function_tool (async) để LLM gọi song song.

Mỗi tool tự lấy dữ liệu (đã preload sẵn trong store), gọi hàm tính thuần qua
asyncio.to_thread (để chạy đồng thời thật khi LLM gọi nhiều tool trong một lượt),
rồi:
- LƯU kết quả có cấu trúc vào run context (store) — số KHÔNG đi qua LLM.
- TRẢ VỀ cho LLM một dict gọn để đọc và diễn giải.

5 tool đầu độc lập nhau nên gọi song song được; missing_data phụ thuộc kết quả
trước nhưng tự tính lại nếu thiếu, nên vẫn an toàn khi chạy song song.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import date

from agents import RunContextWrapper, function_tool

from app.tools.FinanceAgent.finance_data import load_all
from app.tools.FinanceAgent.invoices import classify_invoices
from app.tools.FinanceAgent.liquidity import analyze_liquidity
from app.tools.FinanceAgent.margin import analyze_margin
from app.tools.FinanceAgent.missing_data import detect_missing_data
from app.tools.FinanceAgent.reconcile import reconcile
from app.tools.FinanceAgent.util import parse_date
from app.tools.FinanceAgent.validate_data import validate_finance_data


@dataclass
class FinanceRunContext:
    """Context truyền vào Runner.run. hooks đọc run_id; tools ghi kết quả vào store.
    Dữ liệu nên được preload vào store['data'] trước khi chạy để tránh nạp trùng
    khi các tool chạy song song."""
    run_id: str
    reference_date: str | None = None
    store: dict = field(default_factory=dict)


async def _data(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    store = ctx.context.store
    if "data" not in store:
        store["data"] = await asyncio.to_thread(load_all)
    return store["data"]


def _today(ctx: RunContextWrapper[FinanceRunContext]) -> date:
    return parse_date(ctx.context.reference_date) or date.today()


@function_tool
async def load_and_validate(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    """Bước 1: Nạp dữ liệu tài chính và kiểm tra tính hợp lệ (toàn vẹn tham chiếu,
    field bắt buộc, phân loại counterparty). Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(validate_finance_data, data)
    ctx.context.store["validation"] = result
    return {
        "data_source": data["source"],
        "readiness": result.readiness,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "customer_counterparties": result.customer_counterparties,
        "external_counterparties": result.external_counterparties,
        "unidentified_counterparties": result.unidentified_counterparties,
        "issues": [asdict(i) for i in result.issues],
    }


@function_tool
async def reconcile_bank(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    """Bước 2: Đối chiếu invoice với bank transaction, tách tiền đã thu thật với
    khoản phải thu; loại góp vốn founder và giao dịch bất thường khỏi confirmed
    cash. Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(reconcile, data["invoices"], data["bank_txn"])
    ctx.context.store["reconciliation"] = result
    return asdict(result)


@function_tool
async def liquidity_funding(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    """Bước 3: Tính reserve gap từng tháng và funding need; bật cờ human approval
    nếu vượt ngưỡng governance. Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(analyze_liquidity, data["cashflow"], data["profile"])
    ctx.context.store["liquidity"] = result
    return asdict(result)


@function_tool
async def classify_invoice(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    """Bước 4: Phân loại invoice paid / open / overdue / not-issued (overdue tự suy
    từ status Open và due_date đã qua ngày tham chiếu). Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(classify_invoices, data["invoices"], _today(ctx))
    ctx.context.store["invoices"] = result
    return asdict(result)


@function_tool
async def margin_analysis(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    """Bước 5: Phân tích margin theo order/hợp đồng/danh mục, so target; báo cả
    full-book lẫn committed-only. Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(analyze_margin, data["orders"], data["contracts"],
                                     data["profile"], data["services"])
    ctx.context.store["margin"] = result
    return asdict(result)


@function_tool
async def missing_data(ctx: RunContextWrapper[FinanceRunContext]) -> dict:
    """Bước 6: Tổng hợp dữ liệu còn thiếu (bám điều kiện thật). Nên gọi SAU 5 tool
    trên; nếu thiếu kết quả trước, tool tự tính lại nên vẫn an toàn."""
    data = await _data(ctx)
    store = ctx.context.store
    reconciliation = store.get("reconciliation") or await asyncio.to_thread(
        reconcile, data["invoices"], data["bank_txn"])
    invoice_class = store.get("invoices") or await asyncio.to_thread(
        classify_invoices, data["invoices"], _today(ctx))
    validation = store.get("validation") or await asyncio.to_thread(
        validate_finance_data, data)
    items = await asyncio.to_thread(detect_missing_data, data, reconciliation, invoice_class, validation)
    ctx.context.store["missing"] = items
    return {"count": len(items), "items": [asdict(i) for i in items]}


FINANCE_TOOLS = [
    load_and_validate,
    reconcile_bank,
    liquidity_funding,
    classify_invoice,
    margin_analysis,
    missing_data,
]
