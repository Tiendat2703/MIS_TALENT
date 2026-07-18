"""Deterministic persistence for the Finance → Risk → Decision handoff channel."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.database.repository import query_db
from app.schema.decisionAgent import DecisionBatchOutput
from app.schema.handoff_packs import (
    FinanceBatchPack,
    RiskBatchPack,
    StrictModel,
)


class PipelineContextRecord(StrictModel):
    session_id: int = Field(gt=0)
    finance_pack: FinanceBatchPack
    risk_pack: RiskBatchPack | None = None
    decision_pack: DecisionBatchOutput | None = None


def validate_pipeline_schema() -> None:
    """Fail fast before a run can mix bigint context ids with legacy UUID logs."""
    rows = query_db(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND (
              (table_name = 'context' AND column_name = 'session_id')
              OR (table_name = 'LogsAgent' AND column_name = 'id')
          )
        """
    )
    observed = {
        (row["table_name"], row["column_name"]): row["data_type"]
        for row in rows or []
    }
    expected = {
        ("context", "session_id"): "bigint",
        ("LogsAgent", "id"): "bigint",
    }
    if observed != expected:
        raise RuntimeError(
            "Pipeline database schema is not ready for one bigint id. Apply "
            "supabase/migrations/202607180001_unify_pipeline_session_id.sql. "
            f"Observed={observed}"
        )


def allocate_session_id() -> int:
    """Reserve the bigint identity before any pipeline agent starts."""
    rows = query_db(
        "SELECT nextval(pg_get_serial_sequence('public.context', 'session_id')) "
        "AS session_id"
    )
    if not rows:
        raise RuntimeError("Could not allocate a pipeline session id")
    session_id = int(rows[0]["session_id"])
    if session_id <= 0:
        raise RuntimeError("Database returned an invalid pipeline session id")
    return session_id


def insert_finance_pack(session_id: int, finance_pack: FinanceBatchPack) -> None:
    """Finance owns row creation; rerunning Finance resets downstream packs."""
    rows = query_db(
        """
        INSERT INTO public.context (session_id, finance_pack, risk_pack, decision_pack)
        VALUES (%s, %s::json, NULL, NULL)
        ON CONFLICT (session_id) DO UPDATE SET
            finance_pack = EXCLUDED.finance_pack,
            risk_pack = NULL,
            decision_pack = NULL
        RETURNING session_id
        """,
        (session_id, finance_pack.model_dump_json()),
    )
    if not rows or int(rows[0]["session_id"]) != session_id:
        raise RuntimeError("Finance handoff was not persisted")


def load_pipeline_context(session_id: int) -> PipelineContextRecord:
    rows = query_db(
        """
        SELECT session_id, finance_pack, risk_pack, decision_pack
        FROM public.context
        WHERE session_id = %s
        """,
        (session_id,),
    )
    if not rows:
        raise LookupError(f"Pipeline context not found: session_id={session_id}")
    return PipelineContextRecord.model_validate(rows[0])


def load_finance_pack(session_id: int) -> FinanceBatchPack:
    return load_pipeline_context(session_id).finance_pack


def load_decision_inputs(session_id: int) -> tuple[FinanceBatchPack, RiskBatchPack]:
    record = load_pipeline_context(session_id)
    if record.risk_pack is None:
        raise LookupError(f"RiskPack is not ready for session_id={session_id}")
    return record.finance_pack, record.risk_pack


def save_risk_pack(session_id: int, risk_pack: RiskBatchPack) -> None:
    finance_pack = load_finance_pack(session_id)
    if risk_pack.contract_ids != finance_pack.contract_ids:
        raise ValueError("RiskBatchPack contracts do not match FinanceBatchPack")
    rows = query_db(
        """
        UPDATE public.context
        SET risk_pack = %s::json
        WHERE session_id = %s
          AND finance_pack IS NOT NULL
        RETURNING session_id
        """,
        (
            risk_pack.model_dump_json(),
            session_id,
        ),
    )
    if not rows:
        raise LookupError(
            f"Context {session_id} does not match RiskBatchPack contracts"
        )


def save_decision_pack(session_id: int, decision_pack: DecisionBatchOutput) -> None:
    expected_contract_ids = load_finance_pack(session_id).contract_ids
    returned_ids = [item.contract_id for item in decision_pack.decisions]
    if returned_ids != expected_contract_ids:
        raise ValueError(
            "DecisionPack must contain all context contracts in order: "
            f"expected={expected_contract_ids}, returned={returned_ids}"
        )
    rows = query_db(
        """
        UPDATE public.context
        SET decision_pack = %s::json
        WHERE session_id = %s
          AND risk_pack IS NOT NULL
        RETURNING session_id
        """,
        (decision_pack.model_dump_json(), session_id),
    )
    if not rows:
        raise LookupError(f"Context {session_id} is not ready for a DecisionPack")


def decision_input_payload(session_id: int) -> dict[str, Any]:
    finance_pack, risk_pack = load_decision_inputs(session_id)
    risk_by_contract = {pack.contract_id: pack for pack in risk_pack.packs}
    return {
        "session_id": session_id,
        "contract_ids": finance_pack.contract_ids,
        "portfolio_finance": finance_pack.portfolio_analysis,
        "cases": [
            {
                "finance": pack.model_dump(mode="json"),
                "risk": risk_by_contract[pack.contract_id].model_dump(mode="json"),
                "funding_need": {
                    "need_type": pack.funding_need_type,
                    "requested_amount": pack.requested_amount,
                    "tenor": pack.tenor,
                    "basis": f"Contract {pack.contract_id}",
                },
            }
            for pack in finance_pack.packs
        ],
    }


__all__ = [
    "PipelineContextRecord",
    "allocate_session_id",
    "decision_input_payload",
    "insert_finance_pack",
    "load_decision_inputs",
    "load_finance_pack",
    "load_pipeline_context",
    "save_decision_pack",
    "save_risk_pack",
    "validate_pipeline_schema",
]
