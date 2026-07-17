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
import json
import os
import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from app.Agent.bus import event_bus
from app.schema.financeAgent import FinanceFeaturePack, FinanceSynthesis
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
    "margin_analysis, missing_data), rồi tổng hợp thành FinanceSynthesis dựa hoàn "
    "toàn trên số các tool trả về."
)


def load_prompt(path: Path = PROMPT_PATH) -> str:
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError(f"Prompt rỗng: {path}")
    return prompt


# Agent (LLM + tools) tạo trễ để module import được cả khi chưa cài `agents`.
_AGENT = None


def _get_agent():
    global _AGENT
    if _AGENT is None:
        from agents import Agent, ModelSettings, OpenAIChatCompletionsModel
        from app.Agent.config import OPENAI_CLIENT, OPENAI_MODEL
        from app.Agent.hooks import CustomAgentHooks
        from app.tools.FinanceAgent.tools import FINANCE_TOOLS

        _AGENT = Agent(
            name="Finance_Agent",
            model=OpenAIChatCompletionsModel(model=OPENAI_MODEL, openai_client=OPENAI_CLIENT),
            instructions=load_prompt(),
            output_type=FinanceSynthesis,
            tools=FINANCE_TOOLS,
            # Cho phép LLM gọi nhiều tool trong một lượt -> SDK chạy chúng song song.
            model_settings=ModelSettings(parallel_tool_calls=True),
            hooks=CustomAgentHooks("FinanceAgent"),
        )
    return _AGENT


# ---------- helpers ----------
async def _emit(run_id: str, payload: dict) -> None:
    await event_bus.emit(run_id, payload)


async def _step(run_id: str, step: int, title: str, status: str, summary: str | None = None) -> None:
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
        "validation": asdict(store["validation"]),
        "reconciliation": asdict(store["reconciliation"]),
        "liquidity_brief": asdict(store["liquidity"]),
        "invoice_classification": asdict(store["invoices"]),
        "margin_analysis": asdict(store["margin"]),
        "missing_data_request": [asdict(m) for m in store["missing"]],
    }


def _fallback_synthesis(facts: dict) -> FinanceSynthesis:
    """Diễn giải rule-based khi không gọi được LLM, để luồng vẫn chạy đủ."""
    val = facts["validation"]
    liq = facts["liquidity_brief"]
    rec = facts["reconciliation"]
    inv = facts["invoice_classification"]
    mar = facts["margin_analysis"]
    mdata = facts["missing_data_request"]

    if val["error_count"] > 0:
        readiness = "Insufficient"
    elif liq["funding_need"] > 0 or mdata or mar["margin_pressure_flag"]:
        readiness = "Conditional"
    else:
        readiness = "Ready"

    n_below = len(liq["months_below_reserve"])
    if n_below >= 3 or liq["max_reserve_gap"] >= 500_000_000:
        pressure = "High"
    elif n_below >= 1:
        pressure = "Medium"
    else:
        pressure = "Low"

    if val["error_count"] > 0:
        confidence = "Low"
    elif val["warning_count"] > 0 or mdata:
        confidence = "Medium"
    else:
        confidence = "High"

    low = ", ".join(mar["low_margin_contracts"]) or "không có"
    margin_interp = (f"Margin danh mục {mar['portfolio_margin_pct'] * 100:.1f}% so với target "
                     f"{mar['target_margin_pct'] * 100:.1f}%. Hợp đồng dưới target: {low}.")

    attention: list[str] = []
    if liq["months_below_reserve"]:
        attention.append(f"Áp lực thanh khoản {n_below} tháng, funding need {money(liq['funding_need'])}.")
    if rec["open_without_cash_in"]:
        attention.append("Kiểm tra khả năng thu các invoice Open chưa có tiền về.")
    if rec["suspicious_credits"]:
        attention.append("Có giao dịch đáng ngờ cần soi (chuyển Risk).")
    if mar["margin_pressure_flag"]:
        attention.append("Margin dưới target, cần soi rủi ro thực hiện.")
    if mdata:
        attention.append(f"{len(mdata)} mục dữ liệu còn thiếu cần bổ sung.")

    summary = (f"OPC có funding need {money(liq['funding_need'])}, {n_below} tháng dưới ngưỡng dự trữ. "
               f"Confirmed cash {money(rec['confirmed_cash_total'])}; open AR chưa thu; "
               f"not-issued {money(inv['not_issued_total'])} là upside chưa chắc chắn. "
               f"Margin danh mục {mar['portfolio_margin_pct'] * 100:.1f}% so target {mar['target_margin_pct'] * 100:.1f}%.")

    return FinanceSynthesis(readiness, pressure, confidence, margin_interp, attention, summary)


async def _run_steps_deterministic(run_id: str, store: dict, today: date) -> None:
    """Fallback: tự chạy 6 bước có bắn event (khi không dùng LLM)."""
    await _step(run_id, 1, "Bước 1/6: Load & validate dữ liệu", "start")
    data = store.get("data") or load_all()  # dùng data đã preload (đã áp scenario/submission)
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


def _assemble(run_id: str, store: dict, synthesis: FinanceSynthesis, source: str,
              run_log: list[dict], form, status: str, submission_report) -> FinanceFeaturePack:
    liquidity = store["liquidity"]
    margin = store["margin"]
    signals = {
        "finance_readiness_status": synthesis.finance_readiness_status,
        "liquidity_pressure_level": synthesis.liquidity_pressure_level,
        "data_confidence": synthesis.data_confidence,
        "reserve_breach_flag": liquidity.max_reserve_gap > 0,
        "margin_pressure_flag": margin.margin_pressure_flag,
        "stress_month_count": len(liquidity.months_below_reserve),
        "funding_need": liquidity.funding_need,
        "requires_human_approval": liquidity.requires_human_approval,
        "risk_agent_attention_points": synthesis.risk_agent_attention_points,
        "synthesis_source": source,
    }
    metadata = {
        "agent": "Finance Agent",
        "analysis_id": f"FIN-{run_id[:8]}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "portfolio",
        "data_source": store["data"]["source"],
        "scenario": store["data"].get("scenario"),
        "orchestration": "agentic" if source == "llm" else "deterministic",
        "input_tables": INPUT_TABLES,
        "output_for": "Risk Agent",
        "final_decision_allowed": False,
    }
    return FinanceFeaturePack(
        metadata=metadata,
        liquidity_brief=liquidity,
        invoice_classification=store["invoices"],
        bank_reconciliation_summary=store["reconciliation"],
        margin_analysis=margin,
        missing_data_request=store["missing"],
        financial_capacity_signals=signals,
        handoff_summary=synthesis.handoff_summary,
        status=status,
        data_request_form=form if form.fields else None,
        submission_report=submission_report,
        agent_run_log=run_log,
    )


# ---------- orchestrator ----------
async def run_finance_agent(
    run_id: str | None = None,
    reference_date: date | None = None,
    scenario: str | None = None,
    submission: dict | None = None,
) -> FinanceFeaturePack:
    """Chạy Finance Agent.

    scenario: đường dẫn tệp cấu hình tình huống (vd ca thiếu dữ liệu).
    submission: {field_id: value} người dùng vừa điền vào form yêu cầu bổ sung —
    agent áp các giá trị này rồi chạy tiếp; trường không điền vẫn để thiếu.
    """
    run_id = run_id or str(uuid.uuid4())
    today = _resolve_reference_date(reference_date)
    run_log: list[dict] = []

    await _emit(run_id, {"type": "run_started", "agent": "Finance_Agent",
                         "task": "Finance Agent bắt đầu", "status": "running"})

    # Nạp dữ liệu MỘT lần (đọc từ tệp cấu hình + tình huống), áp dữ liệu người dùng
    # vừa điền (nếu có). Chỉ dùng giá trị người dùng cung cấp — không bịa.
    data = load_all(scenario=scenario)
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
            from app.tools.FinanceAgent.tools import FinanceRunContext

            ctx = FinanceRunContext(run_id=run_id, reference_date=str(today), store=store)
            result = await Runner.run(_get_agent(), input=_ANALYSIS_REQUEST, context=ctx, max_turns=15)
            store = ctx.store
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
                             "data": asdict(form)})

    pack = _assemble(run_id, store, synthesis, source, run_log, form, status, submission_report)

    await _emit(run_id, {"type": "run_finished", "agent": "Finance_Agent",
                         "task": "Finance Agent hoàn tất", "status": "done",
                         "data": {"analysis_id": pack.metadata["analysis_id"],
                                  "status": status,
                                  "funding_need": store["liquidity"].funding_need,
                                  "readiness": synthesis.finance_readiness_status,
                                  "orchestration": pack.metadata["orchestration"]}})
    return pack


if __name__ == "__main__":
    SCENARIO = str(Path(__file__).resolve().parents[1]
                   / "tools" / "FinanceAgent" / "scenarios" / "missing_data_demo.json")

    async def main():
        print("=" * 70)
        print("PHA 1 — Chạy với tình huống THIẾU dữ liệu (đọc từ tệp cấu hình)")
        print("=" * 70)
        pack1 = await run_finance_agent(run_id="demo-missing-01",
                                        reference_date=date(2026, 7, 17), scenario=SCENARIO)
        print("status:", pack1.status)
        print("tháng thiếu projected_closing_cash:", pack1.liquidity_brief.months_missing_data)
        print("order thiếu revenue/cost:", pack1.margin_analysis.orders_missing_data)
        if pack1.data_request_form:
            print(f"\nFORM YÊU CẦU BỔ SUNG ({pack1.data_request_form.form_id}):")
            print(" ", pack1.data_request_form.description)
            for f in pack1.data_request_form.fields:
                req = "bắt buộc" if f.required else "tùy chọn"
                print(f"  • [{f.field_id}] {f.label} — kiểu {f.data_type}, {req}\n    lý do: {f.reason}")

        # Người dùng điền form. Đây là giá trị THẬT do người dùng cung cấp;
        # agent KHÔNG tự bịa. Trường nào không điền sẽ vẫn báo thiếu.
        submission = {
            "orders|ORD-004|estimated_cost": 198000000,
            "cashflow|2026-08|projected_closing_cash": -155000000,
        }
        print("\n" + "=" * 70)
        print("PHA 2 — Người dùng điền form, agent nạp và chạy tiếp")
        print("=" * 70)
        print("Người dùng điền:", submission)
        pack2 = await run_finance_agent(run_id="demo-supplemented-01",
                                        reference_date=date(2026, 7, 17),
                                        scenario=SCENARIO, submission=submission)
        print("submission_report:", pack2.submission_report)
        print("status:", pack2.status)
        print("funding_need:", pack2.liquidity_brief.funding_need)
        print("margin portfolio_pct:", pack2.margin_analysis.portfolio_margin_pct)
        print("readiness:", pack2.financial_capacity_signals["finance_readiness_status"])
        print("còn thiếu (months/orders):",
              pack2.liquidity_brief.months_missing_data, pack2.margin_analysis.orders_missing_data)

    asyncio.run(main())
