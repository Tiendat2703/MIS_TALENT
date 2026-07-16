"""
match_bank_product tích hợp với get_bank_products() đọc DB thật (query_db).
Không mock DB — chỉ mock được phần transform (need_type mapping) vì đây là
bảng chuyển đổi nghiệp vụ cố định, không phải dữ liệu.
"""

from dataclasses import asdict
from typing import TypedDict

from agents import function_tool
from app.database.repository import query_db
from app.schema.bank_product import BankProduct


class FundingNeed(TypedDict):
    """Structured input accepted by the bank-product matching tool."""

    need_type: str
    requested_amount: float


def get_bank_products() -> list[BankProduct]:
    products = query_db("SELECT * FROM bank_product")
    if not isinstance(products, list):
        raise RuntimeError("Expected bank_product query to return a list of rows")
    return [BankProduct(**p) for p in products]


PRODUCT_NAME_TO_NEED_TYPE = {
    "Performance bond": "PERFORMANCE_BOND",
    "Trade finance/LC workflow": "TRADE_FINANCE",
    "SME working capital line": "WORKING_CAPITAL",
    "Micro working capital": "WORKING_CAPITAL",
    "Invoice factoring": "RECEIVABLE_FINANCING",
}

# Ngưỡng collateral_ratio chấp nhận được -> CẦN xác nhận lại với nghiệp vụ.
MAX_ACCEPTABLE_COLLATERAL_RATIO = 0.3


def _normalize_product(product: BankProduct) -> dict | None:
    """Chuẩn hóa 1 row BankProduct: ép kiểu số, gắn need_type qua mapping."""
    row = asdict(product)
    need_type = PRODUCT_NAME_TO_NEED_TYPE.get(row["product_name"])
    if need_type is None:
        return None  

    return {
        "bank_product_id": row["bank_product_id"],
        "bank": row["bank"],
        "product_name": row["product_name"],
        "need_type": need_type,
        "minimum_amount": float(row["minimum_amount"]),
        "collateral_ratio": float(row["collateral_ratio"]),
        "annual_rate_or_fee": float(row["annual_rate_or_fee"]),
        "processing_fee_rate": float(row["processing_fee_rate"]),
        "automation_level": row["automation_level"],
    }


def _evaluate_product(funding_need: FundingNeed, product: dict) -> dict | None:
    if product["need_type"] != funding_need["need_type"]:
        return None

    reasons = [f"Need type matches {product['product_name']}."]

    amount_ok = funding_need["requested_amount"] >= product["minimum_amount"]
    reasons.append(
        "Requested amount is above minimum amount."
        if amount_ok else
        f"Requested amount below minimum ({product['minimum_amount']:,.0f})."
    )

    collateral_ok = product["collateral_ratio"] <= MAX_ACCEPTABLE_COLLATERAL_RATIO
    reasons.append(
        f"Collateral ratio {product['collateral_ratio']:.0%} is within acceptable range."
        if collateral_ok else
        f"Collateral ratio {product['collateral_ratio']:.0%} exceeds acceptable range."
    )

    match_status = (
        "MATCHED" if amount_ok and collateral_ok else
        "PARTIAL" if amount_ok or collateral_ok else
        "NO_MATCH"
    )

    return {
        "bank_product_id": product["bank_product_id"],
        "bank": product["bank"],
        "product_name": product["product_name"],
        "annual_rate_or_fee": product["annual_rate_or_fee"],
        "automation_level": product["automation_level"],
        "match_status": match_status,
        "match_reasons": reasons,
        "human_approval_required": True,
        "precheck_status": "PENDING_HUMAN_APPROVAL",
    }


@function_tool
def match_bank_product(funding_need: FundingNeed) -> dict:
    """So khớp funding_need (need_type, requested_amount) với toàn bộ
    bank_product_catalog trong DB. Trả về best_match (ưu tiên MATCHED, rate
    thấp hơn) và all_candidates để so sánh nhiều lựa chọn ngân hàng."""
    catalog = [p for p in (_normalize_product(bp) for bp in get_bank_products()) if p]

    candidates = [c for c in (_evaluate_product(funding_need, p) for p in catalog) if c]
    if not candidates:
        return {"match_status": "NO_MATCH", "match_reasons": ["No product supports this need_type."]}

    candidates.sort(key=lambda c: (c["match_status"] != "MATCHED", c["annual_rate_or_fee"]))
    return {"best_match": candidates[0], "all_candidates": candidates}

if __name__ == "__main__":
    test_cases = [
        {
            "name": "PERFORMANCE_BOND 420tr - chỉ VietinBank có sản phẩm này",
            "funding_need": {"need_type": "PERFORMANCE_BOND", "requested_amount": 520_000_000},
        },
        {
            "name": "WORKING_CAPITAL 80tr - CoopBank Micro phù hợp, VietinBank SME không đạt minimum",
            "funding_need": {"need_type": "WORKING_CAPITAL", "requested_amount": 80_000_000},
        },
        {
            "name": "RECEIVABLE_FINANCING 250tr - PartnerX Invoice factoring",
            "funding_need": {"need_type": "RECEIVABLE_FINANCING", "requested_amount": 250_000_000},
        },
    ]
 
    for case in test_cases:
        print(f"\n{'=' * 60}\n{case['name']}\n{'=' * 60}")
        print(match_bank_product(case["funding_need"]))
