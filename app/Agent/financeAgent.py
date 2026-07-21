"""Finance Agent — orchestrator (kiểu agentic: LLM tự gọi tool).

Luồng:
- LLM (Runner) tự gọi 6 @function_tool (load_and_validate, reconcile_bank,
  liquidity_funding, classify_invoice, margin_analysis, missing_data). Mỗi lần gọi
  tool, hooks bắn event lên event_bus cho FE thấy từng bước.
- Tool tính xong LƯU kết quả có cấu trúc vào run context (store); số KHÔNG đi qua
  LLM. LLM chỉ đọc dict tóm tắt để diễn giải, cuối cùng trả về FinanceSynthesis.
- Sau khi chạy, code ráp Finance Feature Pack = số từ store + diễn giải từ LLM.
- Nếu LLM/agents không khả dụng (thiếu API key, lỗi mạng) hoặc FINANCE_SKIP_LLM=
  true, chạy fallback tất định (tự gọi các hàm tính) để luồng vẫn đủ end-to-end.

Chạy thử:  python -m app.Agent.financeAgent
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import date, datetime, timezone
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.Agent.bus import event_bus
from app.Agent.prompt_loader import load_prompt
from app.schema.financeAgent import FinanceAnalysisPack, FinanceSynthesis
from app.tools.FinanceAgent.data_request import apply_form_submission, build_data_request_form
from app.tools.FinanceAgent.finance_data import load_all
from app.tools.FinanceAgent.invoices import classify_invoices
from app.tools.FinanceAgent.liquidity import analyze_liquidity
from app.tools.FinanceAgent.margin import analyze_margin
from app.tools.FinanceAgent.missing_data import detect_missing_data
from app.tools.FinanceAgent.reconcile import reconcile
from app.tools.FinanceAgent.util import money, parse_date
from app.tools.FinanceAgent.validate_data import validate_finance_data

PROMPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "financeAgent.md"

INPUT_TABLES = ["04_CONTRACTS", "06_ORDERS", "07_INVOICES", "08_BANK_TXN", "09_CASHFLOW",
                "02_OPC_PROFILE", "03_CUSTOMERS", "05_PRODUCTS"]

_ANALYSIS_REQUEST = (
    "Hãy phân tích sức khỏe tài chính của OPC. Gọi lần lượt đủ 6 tool để lấy các "
    "chỉ số (load_and_validate, reconcile_bank, liquidity_funding, classify_invoice, "
    "margin_analysis, missing_data), rồi viết handoff_summary TÓM TẮT SỐ LIỆU dựa "
    "hoàn toàn trên số các tool trả về. Không đánh giá rủi ro, không kết luận."
)


# Agent (LLM + tools) tạo trễ để module import được cả khi chưa cài `agents`.
_AGENT = None


def build_finance_agent(
    *,
    handoffs: Sequence[Any] = (),
    include_handoff_tool: bool = False,
):
    """Build Finance Agent.

    ``include_handoff_tool`` đăng ký ``prepare_finance_handoff`` (persist
    FinanceBatchPack) ngay cả khi KHÔNG có handoff xuống Risk — dùng cho orchestrator
    gate chạy Finance rời rạc rồi để Validator kiểm trước khi sang Risk.
    """
    from agents import Agent, ModelSettings, OpenAIChatCompletionsModel
    from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
    from app.Agent.config import OPENAI_MODEL, get_openai_client
    from app.Agent.hooks import CustomAgentHooks
    from app.tools.FinanceAgent.tools import FINANCE_TOOLS
    from app.tools.pipeline import prepare_finance_handoff

    prompt = load_prompt(PROMPT_PATH)
    if handoffs:
        prompt = prompt_with_handoff_instructions(prompt)
    want_handoff_tool = bool(handoffs) or include_handoff_tool
    return Agent(
        name="Finance_Agent",
        model=OpenAIChatCompletionsModel(
            model=OPENAI_MODEL,
            openai_client=get_openai_client(),
        ),
        instructions=prompt,
        output_type=FinanceSynthesis,
        tools=[*FINANCE_TOOLS, *([prepare_finance_handoff] if want_handoff_tool else [])],
        handoffs=list(handoffs),
        model_settings=ModelSettings(parallel_tool_calls=True),
        hooks=CustomAgentHooks("Finance_Agent"),
    )


def _get_agent():
    global _AGENT
    if _AGENT is None:
        _AGENT = build_finance_agent()
    return _AGENT


# ---------- helpers ----------
async def _emit(run_id: str | int, payload: dict) -> None:
    await event_bus.emit(run_id, payload)


async def _step(run_id: str | int, step: int, title: str, status: str, summary: str | None = None) -> None:
    payload = {
        "type": "finance_step",
        "agent": "Finance_Agent",
        "step": step,
        "task": title,
        "status": "running" if status == "start" else "done",
    }
    if summary:
        payload["summary"] = summary
    await _emit(run_id, payload)


def _resolve_reference_date(reference_date: date | None) -> date:
    if reference_date:
        return reference_date
    env = os.getenv("FINANCE_REFERENCE_DATE")
    if env:
        return parse_date(env) or date.today()
    return date.today()


def _ensure_results(store: dict, today: date) -> dict:
    """Bù các kết quả chưa có (phòng khi LLM bỏ sót tool, hoặc chạy fallback)."""
    data = store.get("data") or load_all()
    store["data"] = data
    store.setdefault("validation", validate_finance_data(data))
    store.setdefault("reconciliation", reconcile(data["invoices"], data["bank_txn"]))
    store.setdefault("liquidity", analyze_liquidity(data["cashflow"], data["profile"]))
    store.setdefault("invoices", classify_invoices(data["invoices"], today=today))
    store.setdefault("margin", analyze_margin(data["orders"], data["contracts"], data["profile"], data["services"]))
    store.setdefault("missing", detect_missing_data(data, store["reconciliation"], store["invoices"], store["validation"]))
    return store


def _facts_from_store(store: dict) -> dict:
    return {
        "validation": store["validation"].model_dump(mode="json"),
        "reconciliation": store["reconciliation"].model_dump(mode="json"),
        "liquidity_brief": store["liquidity"].model_dump(mode="json"),
        "invoice_classification": store["invoices"].model_dump(mode="json"),
        "margin_analysis": store["margin"].model_dump(mode="json"),
        "missing_data_request": [m.model_dump(mode="json") for m in store["missing"]],
    }


def _fallback_synthesis(facts: dict) -> FinanceSynthesis:
    """Tóm tắt SỐ LIỆU (rule-based) khi không gọi được LLM. Chỉ nêu con số, không
    đánh giá rủi ro/readiness/human-approval."""
    liq = facts["liquidity_brief"]
    rec = facts["reconciliation"]
    inv = facts["invoice_classification"]
    mar = facts["margin_analysis"]
    mdata = facts["missing_data_request"]

    n_below = len(liq["months_below_reserve"])
    summary = (
        f"Funding need {money(liq['funding_need'])}; {n_below} tháng dưới ngưỡng dự trữ "
        f"(tối đa reserve gap {money(liq['max_reserve_gap'])}). "
        f"Confirmed cash {money(rec['confirmed_cash_total'])}; overdue {money(inv['overdue_total'])}; "
        f"open {money(inv['open_current_total'])}; not-issued {money(inv['not_issued_total'])}. "
        f"Margin danh mục {mar['portfolio_margin_pct'] * 100:.1f}% so target {mar['target_margin_pct'] * 100:.1f}%. "
        f"{len(mdata)} mục dữ liệu còn thiếu."
    )
    return FinanceSynthesis(handoff_summary=summary)


async def _run_steps_deterministic(run_id: str | int, store: dict, today: date) -> None:
    """Fallback: tự chạy 6 bước có bắn event (khi không dùng LLM)."""
    await _step(run_id, 1, "Bước 1/6: Load & validate dữ liệu", "start")
    data = store.get("data") or load_all()  # dùng dữ liệu DB đã preload/submission
    store["data"] = data
    store["validation"] = validate_finance_data(data)
    await _step(run_id, 1, "Bước 1/6: Load & validate", "done",
                f"source={data['source']}, readiness={store['validation'].readiness}")

    await _step(run_id, 2, "Bước 2/6: Reconcile invoice ↔ bank txn", "start")
    store["reconciliation"] = reconcile(data["invoices"], data["bank_txn"])
    await _step(run_id, 2, "Bước 2/6: Reconcile", "done",
                f"confirmed cash {money(store['reconciliation'].confirmed_cash_total)}")

    await _step(run_id, 3, "Bước 3/6: Thanh khoản & nhu cầu vốn", "start")
    store["liquidity"] = analyze_liquidity(data["cashflow"], data["profile"])
    await _step(run_id, 3, "Bước 3/6: Liquidity", "done",
                f"funding need {money(store['liquidity'].funding_need)}")

    await _step(run_id, 4, "Bước 4/6: Phân loại invoice", "start")
    store["invoices"] = classify_invoices(data["invoices"], today=today)
    await _step(run_id, 4, "Bước 4/6: Phân loại invoice", "done",
                f"overdue {money(store['invoices'].overdue_total)}, not-issued {money(store['invoices'].not_issued_total)}")

    await _step(run_id, 5, "Bước 5/6: Phân tích margin", "start")
    store["margin"] = analyze_margin(data["orders"], data["contracts"], data["profile"], data["services"])
    await _step(run_id, 5, "Bước 5/6: Margin", "done",
                f"portfolio {store['margin'].portfolio_margin_pct * 100:.1f}% vs target {store['margin'].target_margin_pct * 100:.1f}%")

    await _step(run_id, 6, "Bước 6/6: Missing data request", "start")
    store["missing"] = detect_missing_data(data, store["reconciliation"], store["invoices"], store["validation"])
    await _step(run_id, 6, "Bước 6/6: Missing data", "done", f"{len(store['missing'])} mục cần bổ sung")


def assemble_finance_analysis(
    run_id: str | int,
    store: dict,
    synthesis: FinanceSynthesis,
    source: str,
    run_log: list[dict],
    form,
    status: str,
    submission_report,
) -> FinanceAnalysisPack:
    liquidity = store["liquidity"]
    margin = store["margin"]
    reconciliation = store["reconciliation"]
    invoice_class = store["invoices"]
    validation = store["validation"]
    missing = store["missing"]
    # CHỈ số liệu/sự thật cho Risk — KHÔNG phán đoán (readiness/mức áp lực/human-approval
    # do Risk quyết theo các rule đang hoạt động).
    key_facts = {
        "funding_need": liquidity.funding_need,
        "max_reserve_gap": liquidity.max_reserve_gap,
        "reserve_breach_flag": liquidity.max_reserve_gap > 0,
        "months_below_reserve": liquidity.months_below_reserve,
        "months_negative_cash": liquidity.months_negative_cash,
        "confirmed_cash_total": reconciliation.confirmed_cash_total,
        "open_invoice_current_total": invoice_class.open_current_total,
        "overdue_invoice_total": invoice_class.overdue_total,
        "not_issued_invoice_total": invoice_class.not_issued_total,
        "paid_invoice_total": invoice_class.paid_total,
        "portfolio_margin_pct": margin.portfolio_margin_pct,
        "target_margin_pct": margin.target_margin_pct,
        "margin_gap": margin.margin_gap,
        "margin_below_target": margin.margin_pressure_flag,
        "low_margin_contracts": margin.low_margin_contracts,
        "unmatched_customer_credit_txn": [c.get("txn_id") for c in reconciliation.unmatched_customer_credits],
        "non_operating_credit_txn": [c.get("txn_id") for c in reconciliation.non_operating_credits],
        "suspicious_credit_txn": [c.get("txn_id") for c in reconciliation.suspicious_credits],
        "unidentified_counterparties": validation.unidentified_counterparties,
        "data_error_count": validation.error_count,
        "data_warning_count": validation.warning_count,
        "missing_data_count": len(missing),
        "synthesis_source": source,
    }
    metadata = {
        "agent": "Finance Agent",
        "analysis_id": f"FIN-{run_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "portfolio",
        "data_source": store["data"]["source"],
        "scenario": store["data"].get("scenario"),
        "orchestration": "agentic" if source == "llm" else "deterministic",
        "input_tables": INPUT_TABLES,
        "output_for": "Risk Agent",
        "final_decision_allowed": False,
    }
    return FinanceAnalysisPack(
        metadata=metadata,
        liquidity_brief=liquidity,
        invoice_classification=store["invoices"],
        bank_reconciliation_summary=store["reconciliation"],
        margin_analysis=margin,
        missing_data_request=store["missing"],
        key_facts=key_facts,
        handoff_summary=synthesis.handoff_summary,
        status=status,
        data_request_form=form if form.fields else None,
        submission_report=submission_report,
        agent_run_log=run_log,
    )


# ---------- orchestrator ----------
async def run_finance_agent(
    run_id: int | None = None,
    contract_id: str = "CON-004",
    reference_date: date | None = None,
    submission: dict | None = None,
    persist_context: bool = True,
) -> FinanceAnalysisPack:
    """Chạy Finance Agent.

    submission: {field_id: value} người dùng vừa điền vào form yêu cầu bổ sung —
    agent áp các giá trị này rồi chạy tiếp; trường không điền vẫn để thiếu.
    """
    if persist_context:
        from app.database.context_store import (
            allocate_session_id,
            validate_pipeline_schema,
        )

        validate_pipeline_schema()
        if run_id is None:
            run_id = allocate_session_id()
    elif run_id is None:
        # Local-only analysis still uses a numeric identifier, but it is never
        # presented as a persisted pipeline session.
        run_id = time.time_ns()
    today = _resolve_reference_date(reference_date)
    run_log: list[dict] = []

    await _emit(run_id, {"type": "run_started", "agent": "Finance_Agent",
                         "task": "Finance Agent bắt đầu", "status": "running"})

    # Nạp dữ liệu DB một lần, rồi áp đúng dữ liệu người dùng vừa bổ sung (nếu có).
    data = load_all()
    submission_report = None
    if submission:
        submission_report = apply_form_submission(data, submission)
        run_log.append({"applied_submission": submission_report})
        await _emit(run_id, {"type": "data_supplemented", "agent": "Finance_Agent",
                             "task": "Đã nạp dữ liệu người dùng bổ sung", "status": "running",
                             "summary": f"điền {len(submission_report['filled'])}, "
                                        f"còn thiếu {len(submission_report['still_missing'])}, "
                                        f"không hợp lệ {len(submission_report['invalid'])}"})

    store: dict = {"data": data}
    synthesis: FinanceSynthesis | None = None
    source = "fallback"
    skip = os.getenv("FINANCE_SKIP_LLM", "false").strip().lower() == "true"

    if not skip:
        try:
            from agents import Runner
            from app.Agent.hooks import AppContext

            ctx = AppContext(
                document_id=contract_id,
                original_input=_ANALYSIS_REQUEST,
                run_id=run_id,
                contract_id=contract_id,
                contract_ids=[contract_id],
                reference_date=str(today),
                finance_store=store,
            )
            result = await Runner.run(_get_agent(), input=_ANALYSIS_REQUEST, context=ctx, max_turns=15)
            store = ctx.finance_store
            synthesis = result.final_output
            source = "llm"
            run_log.append({"mode": "agentic", "tools_called": sorted(k for k in store if k not in ("data",))})
        except Exception as exc:  # thiếu agents/API key / lỗi mạng -> fallback
            print(f"[finance] LLM agentic không khả dụng ({exc}); chuyển fallback tất định")
            store, synthesis, source = {"data": data}, None, "fallback"

    if source == "fallback":
        await _run_steps_deterministic(run_id, store, today)
        run_log.append({"mode": "deterministic"})

    _ensure_results(store, today)  # bù nếu LLM bỏ sót tool
    if synthesis is None:
        synthesis = _fallback_synthesis(_facts_from_store(store))
    run_log.append({"synthesis_source": source})

    # Dựng form yêu cầu bổ sung từ các trường THẬT đang thiếu.
    form = build_data_request_form(store["validation"], run_id)
    status = "AWAITING_INPUT" if form.fields else "COMPLETE"
    if form.fields:
        await _emit(run_id, {"type": "data_request_required", "agent": "Finance_Agent",
                             "task": f"Cần bổ sung {len(form.fields)} trường dữ liệu còn thiếu",
                             "status": "awaiting_input",
                             "data": form.model_dump(mode="json")})

    pack = assemble_finance_analysis(
        run_id,
        store,
        synthesis,
        source,
        run_log,
        form,
        status,
        submission_report,
    )

    if persist_context:
        from app.database.context_store import insert_finance_pack
        from app.schema.handoff_packs import FinanceBatchPack
        from app.service.finance_handoff import build_finance_handoff

        handoff_pack = build_finance_handoff(contract_id, pack, store["data"])
        persisted_finance_pack = FinanceBatchPack(
            contract_ids=[contract_id],
            packs=[handoff_pack],
            portfolio_analysis=pack.model_dump(mode="json"),
        )
        insert_finance_pack(run_id, persisted_finance_pack)

    await _emit(run_id, {"type": "run_finished", "agent": "Finance_Agent",
                         "task": "Finance Agent hoàn tất", "status": "done",
                         "data": {"analysis_id": pack.metadata["analysis_id"],
                                  "status": status,
                                  "funding_need": store["liquidity"].funding_need,
                                  "margin_pct": store["margin"].portfolio_margin_pct,
                                  "orchestration": pack.metadata["orchestration"]}})
    if persist_context:
        try:
            from app.tools.writeLogs import persist_agent_stage_log

            persist_agent_stage_log(run_id, "finance", persisted_finance_pack)
        except Exception as exc:
            print(f"[finance] Could not persist FinanceLogs: {type(exc).__name__}: {exc}")
    return pack


if __name__ == "__main__":
    import sys

    # --full: in nguyên FinanceAnalysisPack (JSON) thay vì bản tóm tắt.
    FULL = "--full" in sys.argv

    def _dump_pack(pack) -> None:
        print(pack.model_dump_json(indent=2))

    def _print_summary(pack) -> None:
        print("status:", pack.status)
        print("funding_need:", pack.liquidity_brief.funding_need)
        print("overdue:", pack.invoice_classification.overdue_total)
        print("not_issued:", pack.invoice_classification.not_issued_total)
        print("margin portfolio_pct:", pack.margin_analysis.portfolio_margin_pct,
              "| below_target:", pack.key_facts["margin_below_target"])
        print("missing_data_count:", pack.key_facts["missing_data_count"])
        print("handoff_summary:", pack.handoff_summary)

    async def run_normal() -> None:
        pack = await run_finance_agent()
        (_dump_pack if FULL else _print_summary)(pack)

    asyncio.run(run_normal())


__all__ = [
    "assemble_finance_analysis",
    "build_finance_agent",
    "run_finance_agent",
]
