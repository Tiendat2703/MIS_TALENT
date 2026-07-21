"""Persistence helpers for new contracts submitted through Finance preflight."""

from __future__ import annotations

from app.database.repository import query_db, transaction_cursor
from app.schema.pipeline_input import ContractUploadPackage


_CONTRACT_ID_LOCK_NAMESPACE = 4_849_583
_CONTRACT_ID_LOCK_RESOURCE = 4_347_214
_NEXT_CONTRACT_NUMBER_SQL = """
    SELECT COALESCE(
        MAX((substring(contract_id FROM '^CON-([0-9]+)$'))::integer),
        0
    ) + 1 AS next_number
    FROM contract
    WHERE contract_id ~ '^CON-[0-9]+$'
"""


class CustomerNotFoundError(ValueError):
    """Raised when a draft references a customer outside the demo catalog."""


def _format_contract_id(number: int) -> str:
    return f"CON-{number:03d}"


def get_next_contract_id_preview() -> str:
    """Return a non-reserved preview; the authoritative ID is allocated on insert."""
    rows = query_db(_NEXT_CONTRACT_NUMBER_SQL)
    if not rows or rows[0].get("next_number") is None:
        raise RuntimeError("Could not calculate the next contract ID")
    return _format_contract_id(int(rows[0]["next_number"]))


def create_contract_with_generated_id(contract: ContractUploadPackage) -> str:
    """Allocate and insert a contract atomically under a transaction-level lock."""
    required_values = {
        "customer_id": contract.customer_id,
        "start_date": contract.start_date,
        "end_date": contract.end_date,
        "description": contract.description,
        "contract_value": contract.contract_value,
        "gross_margin": contract.gross_margin,
        "payment_terms": contract.payment_terms,
    }
    missing = [name for name, value in required_values.items() if value is None]
    if missing:
        raise ValueError(
            "Contract cannot be persisted before preflight: " + ", ".join(missing)
        )

    with transaction_cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM customer WHERE customer_id = %s",
            (contract.customer_id,),
        )
        if cursor.fetchone() is None:
            raise CustomerNotFoundError(str(contract.customer_id))

        # Transaction-level locks work with Supavisor transaction mode and are
        # released automatically on commit/rollback.  No network/LLM work is
        # performed while the lock is held.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            (_CONTRACT_ID_LOCK_NAMESPACE, _CONTRACT_ID_LOCK_RESOURCE),
        )
        cursor.execute(_NEXT_CONTRACT_NUMBER_SQL)
        row = cursor.fetchone()
        if not row or row.get("next_number") is None:
            raise RuntimeError("Could not allocate the next contract ID")
        contract_id = _format_contract_id(int(row["next_number"]))

        cursor.execute(
            """
            INSERT INTO contract (
                contract_id,
                customer_id,
                start_date,
                end_date,
                status,
                description,
                contract_value,
                gross_margin,
                payment_terms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                contract_id,
                contract.customer_id,
                contract.start_date,
                contract.end_date,
                "Pending approval",
                contract.description,
                contract.contract_value,
                contract.gross_margin,
                contract.payment_terms,
            ),
        )

    return contract_id


__all__ = [
    "CustomerNotFoundError",
    "create_contract_with_generated_id",
    "get_next_contract_id_preview",
]
