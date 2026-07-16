"""Read bank transactions from PostgreSQL."""

from agents import function_tool
from pydantic import TypeAdapter

from app.database.repository import query_db
from app.schema.risk_db_models import BankTransaction
from app.tools.RiskAgent._helpers import require_rows
from app.tools.RiskAgent._masking import mask_bank_transaction


def get_bank_transactions_impl(txn_id: str | None = None) -> list[BankTransaction]:
    sql = """
        SELECT txn_id, txn_date, bank, account_id, direction, description,
               amount, counterparty_id, txn_status, transaction_risk_score
        FROM bank_txn
    """
    params = None
    if txn_id is not None:
        sql += " WHERE txn_id = %s"
        params = (txn_id,)
    sql += " ORDER BY txn_date, txn_id"
    rows = query_db(sql, params)
    return [BankTransaction(**row) for row in require_rows(rows, "bank_txn")]


@function_tool
def get_bank_transactions(txn_id: str | None = None) -> list[BankTransaction]:
    """Read bank transactions with restricted identifiers tokenized."""
    return [
        mask_bank_transaction(item)
        for item in get_bank_transactions_impl(txn_id)
    ]


if __name__ == "__main__":
    print(
        TypeAdapter(list[BankTransaction])
        .dump_json(get_bank_transactions_impl(), indent=2)
        .decode("utf-8")
    )
