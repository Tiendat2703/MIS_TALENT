"""Persist a masked Risk Pack in the workflow context table."""

from __future__ import annotations

from typing import Literal

from agents import function_tool

from app.database.repository import query_db
from app.schema.handoff_packs import RiskPack, StrictModel
from app.tools.RiskAgent._helpers import require_rows


class RiskPackSaveResult(StrictModel):
    """Acknowledgement returned after a Risk Pack is persisted."""

    session_id: int
    case_id: str
    contract_id: str
    saved: Literal[True] = True


def save_risk_pack_impl(session_id: int, risk_pack: RiskPack) -> RiskPackSaveResult:
    """Store one Risk Pack as JSON on an existing workflow context row."""
    rows = require_rows(
        query_db(
            """
            UPDATE public.context
            SET risk_pack = %s::json
            WHERE session_id = %s
              AND finance_pack ->> 'case_id' = %s
              AND finance_pack ->> 'contract_id' = %s
            RETURNING session_id
            """,
            (
                risk_pack.model_dump_json(),
                session_id,
                risk_pack.case_id,
                risk_pack.contract_id,
            ),
        ),
        "context",
    )
    if not rows:
        raise LookupError(
            f"Context session_id={session_id} does not exist or does not match "
            "the RiskPack case and contract"
        )

    return RiskPackSaveResult(
        session_id=rows[0]["session_id"],
        case_id=risk_pack.case_id,
        contract_id=risk_pack.contract_id,
    )


@function_tool
def save_risk_pack(session_id: int, risk_pack: RiskPack) -> RiskPackSaveResult:
    """Save one masked RiskPack as JSON on an existing context session."""
    return save_risk_pack_impl(session_id, risk_pack)
