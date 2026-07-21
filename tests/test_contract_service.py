from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Lock

import pytest
from pydantic import ValidationError

from app.schema.pipeline_input import ContractUploadPackage
from app.service import contract_service


def _contract(**overrides) -> ContractUploadPackage:
    payload = {
        "customer_id": "CUS-005",
        "start_date": "2026-08-01",
        "end_date": "2027-02-28",
        "description": "Digital sales setup",
        "contract_value": 1_200_000_000,
        "gross_margin": 0.32,
        "payment_terms": "Milestone payment",
        "requested_amount": None,
        "funding_need_type": None,
        "tenor": None,
    }
    payload.update(overrides)
    return ContractUploadPackage.model_validate(payload)


def test_preview_uses_next_canonical_contract_number(monkeypatch) -> None:
    monkeypatch.setattr(
        contract_service,
        "query_db",
        lambda _sql: [{"next_number": 6}],
    )

    assert contract_service.get_next_contract_id_preview() == "CON-006"


def test_atomic_insert_locks_allocates_and_forces_pending_status(monkeypatch) -> None:
    class FakeCursor:
        def __init__(self):
            self.queries: list[tuple[str, object]] = []
            self.results = iter([{"?column?": 1}, {"next_number": 6}])

        def execute(self, sql, params=None):
            self.queries.append((" ".join(sql.split()), params))

        def fetchone(self):
            return next(self.results)

    cursor = FakeCursor()

    @contextmanager
    def fake_transaction():
        yield cursor

    monkeypatch.setattr(contract_service, "transaction_cursor", fake_transaction)

    contract_id = contract_service.create_contract_with_generated_id(_contract())

    assert contract_id == "CON-006"
    statements = [sql for sql, _params in cursor.queries]
    assert statements[0].startswith("SELECT 1 FROM customer")
    assert statements[1].startswith("SELECT pg_advisory_xact_lock")
    assert statements[2].startswith("SELECT COALESCE")
    assert statements[3].startswith("INSERT INTO contract")
    insert_params = cursor.queries[3][1]
    assert insert_params[0] == "CON-006"
    assert insert_params[4] == "Pending approval"


def test_unknown_customer_aborts_before_id_lock(monkeypatch) -> None:
    class FakeCursor:
        def __init__(self):
            self.queries: list[str] = []

        def execute(self, sql, params=None):
            self.queries.append(" ".join(sql.split()))

        def fetchone(self):
            return None

    cursor = FakeCursor()

    @contextmanager
    def fake_transaction():
        yield cursor

    monkeypatch.setattr(contract_service, "transaction_cursor", fake_transaction)

    with pytest.raises(contract_service.CustomerNotFoundError):
        contract_service.create_contract_with_generated_id(_contract())

    assert len(cursor.queries) == 1
    assert "pg_advisory_xact_lock" not in cursor.queries[0]


def test_concurrent_allocations_receive_distinct_sequential_ids(monkeypatch) -> None:
    class SharedDatabase:
        next_number = 6
        advisory_lock = Lock()

    shared = SharedDatabase()

    class FakeCursor:
        def __init__(self):
            self.result = None
            self.holds_lock = False

        def execute(self, sql, params=None):
            normalized = " ".join(sql.split())
            if normalized.startswith("SELECT 1 FROM customer"):
                self.result = {"?column?": 1}
            elif normalized.startswith("SELECT pg_advisory_xact_lock"):
                shared.advisory_lock.acquire()
                self.holds_lock = True
                self.result = {"pg_advisory_xact_lock": None}
            elif normalized.startswith("SELECT COALESCE"):
                self.result = {"next_number": shared.next_number}
            elif normalized.startswith("INSERT INTO contract"):
                shared.next_number += 1

        def fetchone(self):
            return self.result

    @contextmanager
    def fake_transaction():
        cursor = FakeCursor()
        try:
            yield cursor
        finally:
            if cursor.holds_lock:
                shared.advisory_lock.release()

    monkeypatch.setattr(contract_service, "transaction_cursor", fake_transaction)

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(
            executor.map(
                contract_service.create_contract_with_generated_id,
                [_contract(), _contract()],
            )
        )

    assert sorted(ids) == ["CON-006", "CON-007"]


def test_contract_schema_accepts_financing_percentage_in_payment_terms() -> None:
    contract = _contract(payment_terms="WORKING CAPITAL 25%")

    assert contract.payment_terms == "WORKING CAPITAL 25%"


def test_contract_schema_rejects_empty_payment_terms() -> None:
    with pytest.raises(ValidationError, match="payment_terms"):
        _contract(payment_terms="")
