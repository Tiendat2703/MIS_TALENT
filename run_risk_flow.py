"""Chạy thử luồng Risk Agent đầy đủ (LLM + DB).

- Seed một row public.context khớp finance_pack (để save_risk_pack ghi được).
- Gọi main() của Risk Agent: LLM gọi build_risk_pack -> save_risk_pack.

Chạy: python run_risk_flow.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.Agent.risk_compliance_agent import main
from app.database.repository import query_db
from app.schema.handoff_packs import FinanceFeaturePack

SESSION_ID = 9001


def seed_context(finance_pack: FinanceFeaturePack) -> None:
    """Tạo/ghi đè một row context cho session này với finance_pack tương ứng."""
    query_db(
        """
        INSERT INTO public.context (session_id, finance_pack)
        VALUES (%s, %s::json)
        ON CONFLICT (session_id)
        DO UPDATE SET finance_pack = EXCLUDED.finance_pack, risk_pack = NULL
        """,
        (SESSION_ID, finance_pack.model_dump_json()),
    )
    print(f"[SEED] context session_id={SESSION_ID} sẵn sàng")


async def run() -> None:
    finance_pack = FinanceFeaturePack(
        case_id="CASE-004",
        contract_id="CON-004",
        company_id="OPC-001",
        generated_at=datetime.now(UTC),
        transaction_risk_score=90,
        projected_closing_cash=100_000_000,
        cash_reserve_minimum=550_000_000,
        gross_margin=0.24,
        document_sent_to_partner=False,
        requested_amount=400_000_000,
        confidence_score=0.60,
        delivery_delay_days=10,
        source_record_ids=["CON-004", "TXN-006"],
    )
    seed_context(finance_pack)
    await main(finance_pack, session_id=SESSION_ID)


if __name__ == "__main__":
    asyncio.run(run())
