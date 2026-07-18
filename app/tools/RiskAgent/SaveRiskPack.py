"""Persist a masked Risk Pack in the workflow context table."""

from __future__ import annotations

from typing import Literal

from agents import function_tool

from app.database.context_store import save_risk_pack as persist_risk_pack
from app.schema.handoff_packs import RiskPack, StrictModel


class RiskPackSaveResult(StrictModel):
    """Acknowledgement returned after a Risk Pack is persisted."""

    session_id: int
    case_id: str
    contract_id: str
    saved: Literal[True] = True


def save_risk_pack_impl(session_id: int, risk_pack: RiskPack) -> RiskPackSaveResult:
    """Store one Risk Pack as JSON on an existing workflow context row."""
    persist_risk_pack(session_id, risk_pack)

    return RiskPackSaveResult(
        session_id=session_id,
        case_id=risk_pack.case_id,
        contract_id=risk_pack.contract_id,
    )


@function_tool
def save_risk_pack(session_id: int, risk_pack: RiskPack) -> RiskPackSaveResult:
    """Save one masked RiskPack as JSON on an existing context session."""
    return save_risk_pack_impl(session_id, risk_pack)
