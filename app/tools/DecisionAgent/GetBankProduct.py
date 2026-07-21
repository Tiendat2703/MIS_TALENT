"""Expose the real bank-product catalog to Decision without pre-matching it.

Decision reads each product's name, description, fit note, commercial terms and
limits, then performs the semantic selection itself.  Application guards reuse
the same catalog reader only to verify that the selected row exists and that the
authoritative contract amount meets its objective minimum.
"""

from dataclasses import asdict
from typing import Any

from agents import function_tool

from app.database.repository import query_db
from app.schema.bank_product import BankProduct


_NUMERIC_FIELDS = {
    "annual_rate_or_fee",
    "processing_fee_rate",
    "collateral_ratio",
    "minimum_amount",
}


def get_bank_products() -> list[BankProduct]:
    """Read the complete current catalog in one database query."""
    products = query_db(
        """
        SELECT bank_product_id, bank, product_name, target_segment,
               description, annual_rate_or_fee, processing_fee_rate,
               collateral_ratio, minimum_amount, automation_level, fit_note
        FROM bank_product
        ORDER BY bank_product_id
        """
    )
    if not isinstance(products, list):
        raise RuntimeError("Expected bank_product query to return a list of rows")
    return [BankProduct(**product) for product in products]


def serialize_bank_product(product: BankProduct) -> dict[str, Any]:
    """Return model-friendly JSON while preserving every catalog description."""
    payload = asdict(product)
    for field in _NUMERIC_FIELDS:
        payload[field] = float(payload[field])
    return payload


def load_bank_product_catalog() -> list[dict[str, Any]]:
    """Shared raw catalog reader used by the tool and deterministic guards."""
    return [serialize_bank_product(product) for product in get_bank_products()]


@function_tool
def list_bank_products() -> dict[str, Any]:
    """List bank services for Decision to evaluate; performs no matching.

    The Decision Agent must compare contract payment terms and Finance's
    requested amount with these real catalog rows. This tool intentionally does
    not infer a funding type, score candidates, or choose a best product.
    """
    products = load_bank_product_catalog()
    return {
        "count": len(products),
        "products": products,
        "catalog_scope": "current bank_product rows",
        "selection_owner": "Decision_Agent",
    }


__all__ = [
    "get_bank_products",
    "list_bank_products",
    "load_bank_product_catalog",
    "serialize_bank_product",
]
