"""Deterministic persistence for the Finance → Risk → Decision handoff channel."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import Field

from app.database.repository import query_db
from app.schema.decisionAgent import DecisionBatchOutput
from app.schema.handoff_packs import (
    FinanceBatchPack,
    FinanceFeaturePack,
    RiskBatchPack,
    StrictModel,
)
from app.service.credit_profile import (
    credit_profile_payload,
    load_contract_credit_profiles,
    resolve_contract_funding_need,
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


def _as_json_obj(value: Any) -> Any:
    """Cột json có thể về dạng dict hoặc chuỗi tùy driver — chuẩn hóa về object."""
    if isinstance(value, str):
        import json

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def fetch_context_rows(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Đọc THÔ mọi row context (không ép schema), mới nhất trước.

    Trả nguyên finance/risk/decision pack dạng dict để lớp trên tự bung — chịu được
    cả schema batch mới lẫn pack phẳng cũ, nên KHÔNG bỏ sót hợp đồng nào đã chạy.
    """
    rows = query_db(
        """
        SELECT session_id, finance_pack, risk_pack, decision_pack
        FROM public.context
        ORDER BY session_id DESC
        LIMIT %s OFFSET %s
        """,
        (max(1, limit), max(0, offset)),
    )
    return [
        {
            "session_id": int(row["session_id"]),
            "finance_pack": _as_json_obj(row["finance_pack"]),
            "risk_pack": _as_json_obj(row["risk_pack"]),
            "decision_pack": _as_json_obj(row["decision_pack"]),
        }
        for row in rows or []
    ]


def fetch_context_row(session_id: int) -> dict[str, Any] | None:
    """Đọc THÔ một run theo id (không ép schema). None nếu không có."""
    rows = query_db(
        """
        SELECT session_id, finance_pack, risk_pack, decision_pack
        FROM public.context
        WHERE session_id = %s
        """,
        (session_id,),
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "session_id": int(row["session_id"]),
        "finance_pack": _as_json_obj(row["finance_pack"]),
        "risk_pack": _as_json_obj(row["risk_pack"]),
        "decision_pack": _as_json_obj(row["decision_pack"]),
    }


def count_pipeline_contexts() -> int:
    """Tổng số run đã lưu trong bảng context (cho phân trang dashboard)."""
    rows = query_db("SELECT count(*) AS n FROM public.context")
    return int(rows[0]["n"]) if rows else 0


def list_pipeline_contexts(limit: int = 100, offset: int = 0) -> list[PipelineContextRecord]:
    """Đọc nhiều run, mới nhất trước (session_id lớn hơn = mới hơn).

    Row nào sai schema thì bỏ qua (không làm hỏng cả danh sách dashboard).
    """
    rows = query_db(
        """
        SELECT session_id, finance_pack, risk_pack, decision_pack
        FROM public.context
        ORDER BY session_id DESC
        LIMIT %s OFFSET %s
        """,
        (max(1, limit), max(0, offset)),
    )
    records: list[PipelineContextRecord] = []
    for row in rows or []:
        try:
            records.append(PipelineContextRecord.model_validate(row))
        except Exception as exc:  # row cũ/lệch schema -> bỏ qua, ghi log gọn một dòng
            print(
                "[context_store] skip legacy/malformed context row "
                f"session_id={row.get('session_id')} ({type(exc).__name__})"
            )
    return records


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
    finance_pack = load_finance_pack(session_id)
    expected_contract_ids = finance_pack.contract_ids
    returned_ids = [item.contract_id for item in decision_pack.decisions]
    if returned_ids != expected_contract_ids:
        raise ValueError(
            "DecisionPack must contain all context contracts in order: "
            f"expected={expected_contract_ids}, returned={returned_ids}"
        )
    from app.service.decision_guard import validate_decision_finance_consistency

    credit_profiles = load_contract_credit_profiles(finance_pack.contract_ids)
    validate_decision_finance_consistency(
        decision_pack,
        finance_pack,
        credit_profiles,
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
    credit_profiles = load_contract_credit_profiles(finance_pack.contract_ids)
    portfolio_finance = deepcopy(finance_pack.portfolio_analysis)
    reconciliation = portfolio_finance.get("bank_reconciliation_summary")
    if isinstance(reconciliation, dict) and "confirmed_cash_total" in reconciliation:
        reconciliation["confirmed_invoice_collections"] = reconciliation.pop(
            "confirmed_cash_total"
        )

    def build_case(pack: FinanceFeaturePack) -> dict[str, Any]:
        details = pack.finance_details or {}
        finance_payload = pack.model_dump(mode="json")
        # Decision receives the explicitly scoped replacement below.  Removing
        # the legacy aggregate prevents its generic ``revenue`` field from being
        # mistaken for the authoritative full contract value.
        payload_details = finance_payload.get("finance_details") or {}
        payload_details.pop("contract_margin", None)
        profile = credit_profiles.get(pack.contract_id)
        funding_need = resolve_contract_funding_need(
            pack,
            profile,
        )
        return {
            "finance": finance_payload,
            "risk": risk_by_contract[pack.contract_id].model_dump(mode="json"),
            "credit_profile": credit_profile_payload(profile),
            "contract_financials": {
                "contract_value": pack.contract_value,
                "expected_gross_margin_rate": pack.gross_margin,
                "expected_gross_margin_amount": (
                    details.get("contract_economics") or {}
                ).get("expected_gross_margin_amount"),
                "order_allocation": details.get("order_allocation"),
            },
            "funding_need": funding_need,
            "scope_rules": [
                "contract_value is the authoritative full contract value",
                "order_allocation contains order-scoped amounts only",
                "portfolio_finance metrics apply to the whole company, not this contract",
                "credit_profile requested_amount has priority for an explicitly referenced contract",
                "contract funding need is used only when no contract-scoped credit_profile exists",
                "funding_need.amount_status=MISSING means product type may be matched but bank precheck must not run",
            ],
        }

    return {
        "session_id": session_id,
        "contract_ids": finance_pack.contract_ids,
        "portfolio_finance": portfolio_finance,
        "portfolio_scope_note": (
            "portfolio_finance contains whole-company metrics. In particular, "
            "liquidity_brief.funding_need is not a contract bond/credit amount, and "
            "bank_reconciliation_summary.confirmed_invoice_collections is confirmed "
            "invoice collections rather than the company's available cash balance."
        ),
        "credit_profile_lookup": {
            "source_table": "credit_profile",
            "contract_link": "exact contract id in collateral_or_basis",
            "matched_contract_ids": sorted(credit_profiles),
            "fallback": (
                "Use the contract's own funding need only when no contract-scoped "
                "credit_profile row exists."
            ),
        },
        "cases": [build_case(pack) for pack in finance_pack.packs],
    }


__all__ = [
    "PipelineContextRecord",
    "allocate_session_id",
    "count_pipeline_contexts",
    "decision_input_payload",
    "fetch_context_row",
    "fetch_context_rows",
    "insert_finance_pack",
    "list_pipeline_contexts",
    "load_decision_inputs",
    "load_finance_pack",
    "load_pipeline_context",
    "save_decision_pack",
    "save_risk_pack",
    "validate_pipeline_schema",
]
