"""
Mock output của Finance Agent, dùng để test Decision Agent.
Trong thực tế, tool get_finance_agent_output(contract_id) sẽ query DB/API thật.
"""

FINANCE_AGENT_OUTPUT = {
    "CON-004": {
        "contract_id": "CON-004",
        "requested_amount": 420_000_000,
        "tenor": "Until contract acceptance",
        "funding_need_type": "PERFORMANCE_BOND",
        "projected_cash_inflow": 460_000_000,
        "projected_cash_outflow": 350_000_000,
        "expected_margin": 0.24,
        "cashflow_buffer": 40_000_000,
        "receivable_quality": "GOOD",
        "contract_payment_schedule": [
            {"milestone": "Advance payment", "percent": 0.3, "due_date": "2026-07-10"},
            {"milestone": "Delivery", "percent": 0.5, "due_date": "2026-09-01"},
            {"milestone": "Acceptance", "percent": 0.2, "due_date": "2026-10-15"},
        ],
    },
    "CON-007": {
        "contract_id": "CON-007",
        "requested_amount": 150_000_000,
        "tenor": "90 days",
        "funding_need_type": "WORKING_CAPITAL",
        # Required inputs for precheck_micro_credit.
        "customer_type": "SME",
        "receivable_list": ["AR-CON-007-001"],
        "projected_cash_inflow": 160_000_000,
        "projected_cash_outflow": 155_000_000,
        "expected_margin": 0.05,
        "cashflow_buffer": 5_000_000,
        "receivable_quality": "AVERAGE",
        "contract_payment_schedule": [
            {"milestone": "Full payment", "percent": 1.0, "due_date": "2026-10-01"},
        ],
    },
}


def get_finance_agent_output(contract_id: str) -> dict:
    """Trả về mock finance data theo contract_id. Raise nếu không tồn tại."""
    if contract_id not in FINANCE_AGENT_OUTPUT:
        raise ValueError(f"No finance data found for contract_id={contract_id}")
    return FINANCE_AGENT_OUTPUT[contract_id]
