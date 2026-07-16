from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BankProduct:
    bank_product_id: str
    bank: str
    product_name: str
    target_segment: str
    description: str
    annual_rate_or_fee: Decimal
    processing_fee_rate: Decimal
    collateral_ratio: Decimal
    minimum_amount: Decimal
    automation_level: str
    fit_note: str
