"""
Mock bank_product catalog, dùng để test Decision Agent matching logic.
Trong thực tế lấy từ get_bank_products() query DB thật (bảng bank_product).
"""

BANK_PRODUCT_CATALOG = [
    {
        "bank_product_id": "BANKPROD-002",
        "bank": "VietinBank",
        "product_name": "Performance bond",
        "need_type_supported": "PERFORMANCE_BOND",
        "minimum_amount": 300_000_000,
        "collateral_ratio": 0.2,
        "collateral_basis_accepted": ["CONTRACT"],
        "annual_rate_or_fee": 0.012,
        "processing_fee_rate": 0,
        "automation_level": "API_SUPPORTED",
        "api_id": "API-002",
    },
    {
        "bank_product_id": "BANKPROD-005",
        "bank": "VietinBank",
        "product_name": "Trade finance LC",
        "need_type_supported": "TRADE_FINANCE",
        "minimum_amount": 200_000_000,
        "collateral_ratio": 0.3,
        "collateral_basis_accepted": ["CONTRACT", "SUPPLIER_DOCS"],
        "annual_rate_or_fee": 0.015,
        "processing_fee_rate": 0.002,
        "automation_level": "API_SUPPORTED",
        "api_id": "API-003",
    },
    {
        "bank_product_id": "BANKPROD-011",
        "bank": "Co-opBank",
        "product_name": "Micro working capital loan",
        "need_type_supported": "WORKING_CAPITAL",
        "minimum_amount": 50_000_000,
        "collateral_ratio": 0.1,
        "collateral_basis_accepted": ["RECEIVABLE"],
        "annual_rate_or_fee": 0.018,
        "processing_fee_rate": 0.001,
        "automation_level": "API_SUPPORTED",
        "api_id": "API-007",
    },
]


def get_bank_products() -> list[dict]:
    """Trả về toàn bộ mock bank product catalog."""
    return BANK_PRODUCT_CATALOG
