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
from datetime import date

from agents import RunContextWrapper, function_tool

from app.Agent.hooks import AppContext
from app.tools.FinanceAgent.finance_data import get_services, load_all
from app.tools.FinanceAgent.invoices import classify_invoices
from app.tools.FinanceAgent.liquidity import analyze_liquidity
from app.tools.FinanceAgent.margin import analyze_margin
from app.tools.FinanceAgent.missing_data import detect_missing_data
from app.tools.FinanceAgent.reconcile import reconcile
from app.tools.FinanceAgent.util import parse_date
from app.tools.FinanceAgent.validate_data import validate_finance_data


# Compatibility name for older imports.  The integrated pipeline uses one
# AppContext type for Finance, Risk, and Decision as required by Runner.run.
FinanceRunContext = AppContext


async def _data(ctx: RunContextWrapper[AppContext]) -> dict:
    store = ctx.context.finance_store
    if "data" not in store:
        store["data"] = await asyncio.to_thread(load_all)
    return store["data"]


def _today(ctx: RunContextWrapper[AppContext]) -> date:
    return parse_date(ctx.context.reference_date) or date.today()


@function_tool
async def load_service_catalog(ctx: RunContextWrapper[AppContext]) -> dict:
    """Preflight only: load the OPC service catalog for semantic description matching.

    The tool keeps complete rows in the private run context so application code
    can resolve ``target_margin`` after validating the LLM-selected service ID.
    Margin numbers are deliberately omitted from the tool result shown to the
    model; the model's only numeric output is an informational confidence score.
    """
    rows = await asyncio.to_thread(get_services)
    catalog = [dict(row) for row in rows if row.get("service_id")]
    ctx.context.finance_store["service_catalog"] = catalog
    return {
        "count": len(catalog),
        "services": [
            {
                "service_id": row.get("service_id"),
                "service_name": row.get("service_name"),
                "pricing_model": row.get("pricing_model"),
                "target_segment": row.get("target_segment"),
            }
            for row in catalog
        ],
    }


@function_tool
async def load_and_validate(ctx: RunContextWrapper[AppContext]) -> dict:
    """Bước 1: Nạp dữ liệu tài chính và kiểm tra tính hợp lệ (toàn vẹn tham chiếu,
    field bắt buộc, phân loại counterparty). Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(validate_finance_data, data)
    ctx.context.finance_store["validation"] = result
    output = {
        "data_source": data["source"],
        "readiness": result.readiness,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "customer_counterparties": result.customer_counterparties,
        "external_counterparties": result.external_counterparties,
        "unidentified_counterparties": result.unidentified_counterparties,
        "issues": [i.model_dump(mode="json") for i in result.issues],
    }
    if data.get("_preflight_payload_only") is True:
        # Expose only the one field required for semantic catalog matching.
        # The prompt treats it as untrusted data and forbids following embedded
        # instructions.
        output["contract_description"] = (data.get("upload") or {}).get(
            "description"
        )
    return output


@function_tool
async def reconcile_bank(ctx: RunContextWrapper[AppContext]) -> dict:
    """Bước 2: Đối chiếu invoice với bank transaction, tách tiền đã thu thật với
    khoản phải thu; loại góp vốn founder và giao dịch bất thường khỏi confirmed
    cash. Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(reconcile, data["invoices"], data["bank_txn"])
    ctx.context.finance_store["reconciliation"] = result
    return result.model_dump(mode="json")


@function_tool
async def liquidity_funding(ctx: RunContextWrapper[AppContext]) -> dict:
    """Bước 3: Tính reserve gap từng tháng và funding need; bật cờ human approval
    nếu vượt ngưỡng governance. Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(analyze_liquidity, data["cashflow"], data["profile"])
    ctx.context.finance_store["liquidity"] = result
    return result.model_dump(mode="json")


@function_tool
async def classify_invoice(ctx: RunContextWrapper[AppContext]) -> dict:
    """Bước 4: Phân loại invoice paid / open / overdue / not-issued (overdue tự suy
    từ status Open và due_date đã qua ngày tham chiếu). Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(classify_invoices, data["invoices"], _today(ctx))
    ctx.context.finance_store["invoices"] = result
    return result.model_dump(mode="json")


@function_tool
async def margin_analysis(ctx: RunContextWrapper[AppContext]) -> dict:
    """Bước 5: Phân tích margin theo order/hợp đồng/danh mục, so target; báo cả
    full-book lẫn committed-only. Độc lập, có thể gọi song song."""
    data = await _data(ctx)
    result = await asyncio.to_thread(analyze_margin, data["orders"], data["contracts"],
                                     data["profile"], data["services"])
    ctx.context.finance_store["margin"] = result
    return result.model_dump(mode="json")


@function_tool
async def missing_data(ctx: RunContextWrapper[AppContext]) -> dict:
    """Bước 6: Tổng hợp dữ liệu còn thiếu (bám điều kiện thật). Nên gọi SAU 5 tool
    trên; nếu thiếu kết quả trước, tool tự tính lại nên vẫn an toàn."""
    data = await _data(ctx)
    store = ctx.context.finance_store
    reconciliation = store.get("reconciliation") or await asyncio.to_thread(
        reconcile, data["invoices"], data["bank_txn"])
    invoice_class = store.get("invoices") or await asyncio.to_thread(
        classify_invoices, data["invoices"], _today(ctx))
    validation = store.get("validation") or await asyncio.to_thread(
        validate_finance_data, data)
    items = await asyncio.to_thread(detect_missing_data, data, reconciliation, invoice_class, validation)
    ctx.context.finance_store["missing"] = items
    return {
        "count": len(items),
        "items": [item.model_dump(mode="json") for item in items],
    }


FINANCE_TOOLS = [
    load_and_validate,
    reconcile_bank,
    liquidity_funding,
    classify_invoice,
    margin_analysis,
    missing_data,
]
