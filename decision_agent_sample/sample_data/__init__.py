from .bank_product_catalog import get_bank_products
from .finance_agent_output import FINANCE_AGENT_OUTPUT, get_finance_agent_output
from .risk_agent_output import RISK_AGENT_OUTPUT, get_risk_agent_output


def get_mock_contract_ids() -> list[str]:
    """Return every contract that has both finance and risk mock data."""
    finance_ids = set(FINANCE_AGENT_OUTPUT)
    risk_ids = set(RISK_AGENT_OUTPUT)

    if finance_ids != risk_ids:
        missing_finance = sorted(risk_ids - finance_ids)
        missing_risk = sorted(finance_ids - risk_ids)
        raise ValueError(
            "Finance and risk mock data are inconsistent: "
            f"missing finance={missing_finance}, missing risk={missing_risk}"
        )

    return sorted(finance_ids)

__all__ = [
    "get_bank_products",
    "get_finance_agent_output",
    "get_mock_contract_ids",
    "get_risk_agent_output",
]
