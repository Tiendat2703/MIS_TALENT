"""Finance Agent — orchestrator end-to-end.

Kiến trúc (kiểu code cầm lái + LLM tổng hợp):
- Code chạy tuần tự 6 bước tính toán, mỗi bước bắn event lên event_bus cho FE.
- Gom kết quả thành FINANCE_FACTS, gọi LLM MỘT lần để sinh phần diễn giải
  (FinanceSynthesis). LLM không trả lại con số.
- Code ráp số + diễn giải thành FinanceFeaturePack.
- Nếu LLM chưa khả dụng (thiếu API key / lỗi mạng) hoặc FINANCE_SKIP_LLM=true,
  dùng fallback rule-based để luồng vẫn chạy end-to-end.

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


def load_prompt(path: Path = PROMPT_PATH) -> str:
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError(f"Prompt rỗng: {path}")
    return prompt


# Agent (LLM) được tạo trễ để module vẫn import/chạy được khi chưa cài `agents`
# hoặc khi FINANCE_SKIP_LLM=true (lúc đó dùng fallback rule-based).
_AGENT = None


def _get_agent():
    global _AGENT
    if _AGENT is None:
        from agents import Agent, OpenAIChatCompletionsModel
        from app.Agent.config import OPENAI_CLIENT, OPENAI_MODEL
        from app.Agent.hooks import CustomAgentHooks

        _AGENT = Agent(
            name="Finance_Agent",
            model=OpenAIChatCompletionsModel(model=OPENAI_MODEL, openai_client=OPENAI_CLIENT),
            instructions=load_prompt(),
            output_type=FinanceSynthesis,
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


def _fallback_synthesis(facts: dict) -> FinanceSynthesis:
    """Bản diễn giải rule-based khi không gọi được LLM, để luồng vẫn chạy đủ."""
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


async def _synthesize(run_id: str, facts: dict) -> tuple[FinanceSynthesis, str]:
    skip = os.getenv("FINANCE_SKIP_LLM", "false").strip().lower() == "true"
    if not skip:
        try:
            from agents import Runner
            from app.Agent.hooks import AppContext

            ctx = AppContext(document_id=run_id, original_input="finance_synthesis", run_id=run_id)
            user_input = "FINANCE_FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=2, default=str)
            result = await Runner.run(_get_agent(), input=user_input, context=ctx, max_turns=4)
            return result.final_output, "llm"
        except Exception as exc:  # thiếu `agents`/API key / lỗi mạng -> fallback
            print(f"[finance] LLM synthesis không khả dụng ({exc}); dùng fallback rule-based")
    return _fallback_synthesis(facts), "fallback"


# ---------- orchestrator ----------
async def run_finance_agent(run_id: str | None = None, reference_date: date | None = None) -> FinanceFeaturePack:
    run_id = run_id or str(uuid.uuid4())
    today = _resolve_reference_date(reference_date)
    run_log: list[dict] = []

    await _emit(run_id, {"type": "run_started", "agent": "Finance_Agent",
                         "task": "Finance Agent bắt đầu", "status": "running"})

    # Bước 1 — Load & validate
    await _step(run_id, 1, "Bước 1/7: Load & validate dữ liệu", "start")
    data = load_all()
    validation = validate_finance_data(data)
    run_log.append({"step": 1, "action": "load_all + validate", "source": data["source"]})
    await _step(run_id, 1, "Bước 1/7: Load & validate", "done",
                f"source={data['source']}, readiness={validation.readiness}, "
                f"{validation.error_count} lỗi, {validation.warning_count} cảnh báo")

    # Bước 2 — Reconcile
    await _step(run_id, 2, "Bước 2/7: Đối chiếu invoice ↔ bank txn", "start")
    reconciliation = reconcile(data["invoices"], data["bank_txn"])
    run_log.append({"step": 2, "action": "reconcile", "confirmed_cash": reconciliation.confirmed_cash_total})
    await _step(run_id, 2, "Bước 2/7: Reconcile", "done",
                f"confirmed cash {money(reconciliation.confirmed_cash_total)}, "
                f"{len(reconciliation.open_without_cash_in)} invoice open chưa có tiền về")

    # Bước 3 — Liquidity & funding need
    await _step(run_id, 3, "Bước 3/7: Thanh khoản & nhu cầu vốn", "start")
    liquidity = analyze_liquidity(data["cashflow"], data["profile"])
    run_log.append({"step": 3, "action": "analyze_liquidity", "funding_need": liquidity.funding_need})
    await _step(run_id, 3, "Bước 3/7: Liquidity", "done",
                f"funding need {money(liquidity.funding_need)}, "
                f"{len(liquidity.months_below_reserve)}/{len(liquidity.by_month)} tháng dưới ngưỡng dự trữ")

    # Bước 4 — Phân loại invoice
    await _step(run_id, 4, "Bước 4/7: Phân loại invoice", "start")
    invoice_class = classify_invoices(data["invoices"], today=today)
    run_log.append({"step": 4, "action": "classify_invoices", "reference_date": str(today)})
    await _step(run_id, 4, "Bước 4/7: Phân loại invoice", "done",
                f"paid {money(invoice_class.paid_total)}, overdue {money(invoice_class.overdue_total)}, "
                f"open {money(invoice_class.open_current_total)}, not-issued {money(invoice_class.not_issued_total)}")

    # Bước 5 — Margin
    await _step(run_id, 5, "Bước 5/7: Phân tích margin", "start")
    margin = analyze_margin(data["orders"], data["contracts"], data["profile"], data["services"])
    run_log.append({"step": 5, "action": "analyze_margin", "portfolio_margin_pct": margin.portfolio_margin_pct})
    await _step(run_id, 5, "Bước 5/7: Margin", "done",
                f"portfolio {margin.portfolio_margin_pct * 100:.1f}% vs target {margin.target_margin_pct * 100:.1f}%, "
                f"dưới target: {', '.join(margin.low_margin_contracts) or 'không'}")

    # Bước 6 — Missing data
    await _step(run_id, 6, "Bước 6/7: Missing data request", "start")
    missing = detect_missing_data(data, reconciliation, invoice_class, validation)
    run_log.append({"step": 6, "action": "detect_missing_data", "count": len(missing)})
    await _step(run_id, 6, "Bước 6/7: Missing data", "done", f"{len(missing)} mục cần bổ sung")

    # Bước 7 — LLM tổng hợp
    await _step(run_id, 7, "Bước 7/7: LLM tổng hợp & handoff", "start")
    facts = {
        "validation": asdict(validation),
        "reconciliation": asdict(reconciliation),
        "liquidity_brief": asdict(liquidity),
        "invoice_classification": asdict(invoice_class),
        "margin_analysis": asdict(margin),
        "missing_data_request": [asdict(m) for m in missing],
    }
    synthesis, source = await _synthesize(run_id, facts)
    run_log.append({"step": 7, "action": "synthesize", "source": source})
    await _step(run_id, 7, "Bước 7/7: Tổng hợp", "done",
                f"readiness={synthesis.finance_readiness_status}, nguồn diễn giải={source}")

    # Ráp Finance Feature Pack
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
        "data_source": data["source"],
        "input_tables": INPUT_TABLES,
        "output_for": "Risk Agent",
        "final_decision_allowed": False,
    }
    pack = FinanceFeaturePack(
        metadata=metadata,
        liquidity_brief=liquidity,
        invoice_classification=invoice_class,
        bank_reconciliation_summary=reconciliation,
        margin_analysis=margin,
        missing_data_request=missing,
        financial_capacity_signals=signals,
        handoff_summary=synthesis.handoff_summary,
        agent_run_log=run_log,
    )

    await _emit(run_id, {"type": "run_finished", "agent": "Finance_Agent",
                         "task": "Finance Agent hoàn tất", "status": "done",
                         "data": {"analysis_id": metadata["analysis_id"],
                                  "funding_need": liquidity.funding_need,
                                  "readiness": synthesis.finance_readiness_status}})
    return pack


if __name__ == "__main__":
    async def main():
        # Dùng ngày tham chiếu trong khoảng dataset để overdue hiển thị đúng.
        pack = await run_finance_agent(reference_date=date(2026, 7, 17))
        print("\n" + "=" * 70)
        print("FINANCE FEATURE PACK")
        print("=" * 70)
        print(json.dumps(asdict(pack), ensure_ascii=False, indent=2, default=str))

    asyncio.run(main())
