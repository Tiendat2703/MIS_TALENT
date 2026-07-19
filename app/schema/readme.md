# Schema

- `handoff_packs.py`: public handoff contracts between Finance, Risk, and Decision
  agents.
- `risk_db_models.py`: internal PostgreSQL row models used only by query tools.

Public pipeline integrations persist `FinanceBatchPack` and `RiskBatchPack` from
`handoff_packs.py`. Each batch contains ordered contract-scoped
`FinanceFeaturePack` / `RiskPack` records. Finance's portfolio-oriented internal
output is stored once in `FinanceBatchPack.portfolio_analysis`; the adapter in
`service/finance_handoff.py` produces the contract-specific projections.
