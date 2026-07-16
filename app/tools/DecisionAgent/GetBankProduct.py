import json
from dataclasses import asdict

from app.database.repository import query_db
from app.schema.bank_product import BankProduct


def get_bank_products() -> list[BankProduct]:
    products = query_db("SELECT * FROM bank_product")

    if not isinstance(products, list):
        raise RuntimeError("Expected bank_product query to return a list of rows")

    return [BankProduct(**product) for product in products]


def bank_products_to_json(products: list[BankProduct]) -> str:
    """Serialize bank products to formatted JSON without losing Decimal precision."""
    return json.dumps(
        [asdict(product) for product in products],
        default=str,
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    print(bank_products_to_json(get_bank_products()))
