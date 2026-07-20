"""Deterministic tools used at Finance → Risk → Decision boundaries."""

from __future__ import annotations

import asyncio

from agents import RunContextWrapper, function_tool

from app.Agent.hooks import AppContext
from app.database.context_store import (
    decision_input_payload,
    insert_finance_pack,
    load_finance_pack,
    save_risk_pack,
)
from app.schema.financeAgent import FinanceSynthesis
from app.schema.handoff_packs import FinanceBatchPack, RiskBatchPack
from app.tools.FinanceAgent.data_request import build_data_request_form
from app.tools.RiskAgent.BuildRiskReport import build_risk_pack_impl


def _require_session(context: AppContext, session_id: int) -> None:
    if session_id != context.run_id:
        raise PermissionError(
            "Handoff session_id does not match the Runner application context"
        )


@function_tool
async def prepare_finance_handoff(
    context: RunContextWrapper[AppContext],
    session_id: int,
    contract_ids: list[str],
    handoff_summary: str,
) -> dict:
    """Assemble and persist all canonical Finance packs before handing off.

    The six Finance calculation tools must already have populated the local
    store.  This tool never calculates a missing stage on behalf of the model.
    """
    _require_session(context.context, session_id)
    if contract_ids != context.context.contract_ids:
        raise PermissionError("contract_ids do not match the pipeline batch")

    store = context.context.finance_store
    required = {
        "data",
        "validation",
        "reconciliation",
        "liquidity",
        "invoices",
        "margin",
        "missing",
    }
    missing = sorted(required - set(store))
    if missing:
        raise RuntimeError(
            "Finance analysis is incomplete; missing tool results: "
            + ", ".join(missing)
        )

    from app.Agent.financeAgent import assemble_finance_analysis
    from app.service.finance_handoff import build_finance_handoff

    form = build_data_request_form(store["validation"], str(session_id))
    status = "AWAITING_INPUT" if form.fields else "COMPLETE"
    analysis = assemble_finance_analysis(
        session_id,
        store,
        FinanceSynthesis(handoff_summary=handoff_summary),
        "llm",
        [{"mode": "agentic", "tools_called": sorted(required - {"data"})}],
        form,
        status,
        None,
    )
    packs = [
        build_finance_handoff(contract_id, analysis, store["data"])
        for contract_id in contract_ids
    ]
    finance_pack = FinanceBatchPack(
        contract_ids=contract_ids,
        packs=packs,
        portfolio_analysis=analysis.model_dump(mode="json"),
    )
    await asyncio.to_thread(insert_finance_pack, session_id, finance_pack)
    store["analysis_pack"] = analysis
    store["finance_pack"] = finance_pack
    return {
        "session_id": session_id,
        "contract_ids": contract_ids,
        "case_count": len(packs),
        "statuses": {
            pack.contract_id: pack.status for pack in packs
        },
        "persisted": True,
    }


@function_tool
async def process_risk_context(
    context: RunContextWrapper[AppContext],
    session_id: int,
) -> dict:
    """Load Finance by id, build Risk deterministically, and persist Risk by id."""
    _require_session(context.context, session_id)
    finance_pack = await asyncio.to_thread(load_finance_pack, session_id)
    risk_packs = [
        await asyncio.to_thread(build_risk_pack_impl, pack)
        for pack in finance_pack.packs
    ]
    risk_pack = RiskBatchPack(
        contract_ids=finance_pack.contract_ids,
        packs=risk_packs,
    )
    await asyncio.to_thread(save_risk_pack, session_id, risk_pack)
    context.context.finance_store["risk_pack"] = risk_pack
    # Return the exact persisted pack so standalone Risk runs can use it as
    # structured output without reconstructing fields in LLM reasoning.
    return risk_pack.model_dump(mode="json")


@function_tool
async def load_decision_context(
    context: RunContextWrapper[AppContext],
    session_id: int,
) -> dict:
    """Load Finance/Risk and resolve contract amounts from Credit Profile first."""
    _require_session(context.context, session_id)
    return await asyncio.to_thread(decision_input_payload, session_id)


__all__ = [
    "load_decision_context",
    "prepare_finance_handoff",
    "process_risk_context",
]
