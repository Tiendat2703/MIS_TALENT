# Schema

- `handoff_packs.py`: public handoff contracts between Finance, Risk, and Decision
  agents.
- `risk_db_models.py`: internal PostgreSQL row models used only by query tools.

Public agent integrations should import `FinanceFeaturePack` and `RiskPack`
from `handoff_packs.py`.
